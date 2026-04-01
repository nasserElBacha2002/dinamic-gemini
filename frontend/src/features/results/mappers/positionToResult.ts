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

/** Backend traceability is lowercase; visible model uses uppercase.
 * Unknown/missing → UNVALIDATED (document-only fallback: backend sends valid|missing|invalid|unvalidated). */
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
 * Unknown status → DETECTED (document-only: backend sends detected|reviewed|corrected|deleted). */
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

/** Map list position (API) to ResultSummary.
 * v3.2.5 Block 4: has_evidence is canonical. Fallback (Reduce): when has_evidence is not a boolean,
 * use primary_evidence_id only for historical/transitional payloads; do not treat as canonical for fresh API. */
export function mapPositionSummaryToResultSummary(
  p: PositionSummary
): ResultSummary {
  /** Sprint 2: nested blocks first, then deprecated flat aliases, then historical inference. */
  const hasEvidence =
    typeof p.traceability?.has_evidence === 'boolean'
      ? p.traceability.has_evidence
      : typeof p.has_evidence === 'boolean'
        ? p.has_evidence
        : Boolean(
            p.primary_evidence_id != null && String(p.primary_evidence_id).trim() !== ''
          );
  const sku = p.product?.sku ?? p.sku ?? null;
  const detectedQty = p.quantity?.detected ?? p.detected_quantity ?? null;
  const correctedQty = p.quantity?.corrected ?? p.corrected_quantity ?? null;
  const resolvedQty =
    p.quantity?.final ??
    (p.corrected_quantity != null ? p.corrected_quantity : p.qty ?? null);
  const qtySource = p.quantity?.source ?? p.qtySource ?? 'detected';
  const qtyResolved = p.quantity?.resolved ?? p.qtyResolved ?? null;
  const qtyInferenceReason =
    p.quantity?.inference_reason ?? p.qtyInferenceReason ?? null;
  const traceabilityStatus = mapTraceabilityToVisible(
    p.traceability?.status ?? p.traceability_status
  );

  return {
    id: p.id,
    sku,
    positionCode: p.position_code ?? null,
    detectedQty,
    correctedQty,
    resolvedQty,
    qtySource,
    qtyResolved,
    qtyInferenceReason,
    confidence: p.confidence ?? null,
    reviewStatus: mapPositionStatusToReviewStatus(p.status, p.needs_review),
    traceabilityStatus,
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

/** Map review action to ReviewHistoryItem. Phase 6: include before/after for audit summary. */
export function mapReviewActionToHistoryItem(
  a: ReviewActionSummary
): ReviewHistoryItem {
  return {
    id: a.id,
    action: a.action_type,
    createdAt: a.created_at,
    userName: a.user_id ?? undefined,
    notes: a.comment ?? undefined,
    beforeJson: a.before_json ?? undefined,
    afterJson: a.after_json ?? undefined,
  };
}

/** Map position detail response (API) to ResultDetail. */
export function mapPositionDetailToResultDetail(
  data: PositionDetailResponse
): ResultDetail {
  const position = data.position;
  const evidences = data.evidences ?? [];
  const review_actions = data.review_actions ?? [];

  const technicalSnapshot = data.technical_snapshot ?? null;
  /** Canonical: Sprint 2 ``traceability`` block, then typed fields.
   * Sprint 3 removes the frontend dependency on `detected_summary_json`; detail technical metadata
   * now flows through `technical_snapshot` only. */
  const typedSourceImageId =
    (position.traceability?.source_image_id != null &&
      String(position.traceability.source_image_id).trim() !== ''
      ? position.traceability.source_image_id.trim()
      : null) ??
    (position.source_image_id != null && String(position.source_image_id).trim() !== ''
      ? position.source_image_id.trim()
      : null);
  const typedSourceFileName =
    (position.traceability?.source_image_original_filename != null &&
    String(position.traceability.source_image_original_filename).trim() !== ''
      ? position.traceability.source_image_original_filename.trim()
      : null) ??
    (position.source_image_original_filename != null &&
    String(position.source_image_original_filename).trim() !== ''
      ? position.source_image_original_filename.trim()
      : null);
  const sourceImageId = typedSourceImageId;
  const sourceFileName = typedSourceFileName;
  const entityId =
    technicalSnapshot != null &&
    typeof technicalSnapshot === 'object' &&
    'entity_uid' in technicalSnapshot &&
    typeof technicalSnapshot.entity_uid === 'string' &&
    technicalSnapshot.entity_uid.trim() !== ''
      ? technicalSnapshot.entity_uid.trim()
      : null;

  const sku = position.product?.sku ?? position.sku ?? null;
  const detectedQty =
    position.quantity?.detected ?? position.detected_quantity ?? null;
  const correctedQty =
    position.quantity?.corrected ?? position.corrected_quantity ?? null;
  const resolvedQty =
    position.quantity?.final ??
    (position.corrected_quantity != null
      ? position.corrected_quantity
      : position.qty ?? null);
  const systemQty = position.qty ?? null;
  const qtySource = position.quantity?.source ?? position.qtySource ?? 'detected';
  const qtyResolved = position.quantity?.resolved ?? position.qtyResolved ?? null;
  const qtyInferenceReason =
    position.quantity?.inference_reason ?? position.qtyInferenceReason ?? null;
  const traceabilityStatus = mapTraceabilityToVisible(
    position.traceability?.status ?? position.traceability_status
  );

  return {
    id: position.id,
    sku,
    positionCode: position.position_code ?? null,
    detectedQty,
    correctedQty,
    resolvedQty,
    systemQty,
    qtySource,
    qtyResolved,
    qtyInferenceReason,
    confidence: position.confidence ?? null,
    reviewStatus: mapPositionStatusToReviewStatus(
      position.status,
      position.needs_review
    ),
    traceabilityStatus,
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
      primaryEvidenceId:
        position.traceability?.primary_evidence_id ?? position.primary_evidence_id ?? undefined,
      rawStatus: position.status ?? undefined,
    },
  };
}
