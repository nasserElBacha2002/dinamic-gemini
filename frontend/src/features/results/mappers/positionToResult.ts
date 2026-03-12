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
  ProductRecordSummary,
  ReviewActionSummary,
} from '../../../api/types';
import type {
  ResultSummary,
  ResultDetail,
  ResultEvidence,
  ResultProductInfo,
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

/** Map list position (API) to ResultSummary. */
export function mapPositionSummaryToResultSummary(
  p: PositionSummary
): ResultSummary {
  return {
    id: p.id,
    sku: p.sku ?? null,
    detectedQty: p.detected_quantity ?? null,
    confidence: p.confidence ?? null,
    reviewStatus: mapPositionStatusToReviewStatus(p.status, p.needs_review),
    traceabilityStatus: mapTraceabilityToVisible(p.traceability_status),
    needsReview: p.needs_review,
    updatedAt: p.updated_at,
    hasEvidence: Boolean(
      p.primary_evidence_id != null && String(p.primary_evidence_id).trim() !== ''
    ),
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

/** Map product record to ResultProductInfo (first product used as primary product block). */
export function mapProductToResultProductInfo(
  pr: ProductRecordSummary
): ResultProductInfo {
  return {
    productId: pr.id,
    sku: pr.sku,
    description: pr.description ?? undefined,
    correctedQty: pr.corrected_quantity ?? undefined,
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
  const products = data.products ?? [];
  const evidences = data.evidences ?? [];
  const review_actions = data.review_actions ?? [];

  const summaryJson = position.detected_summary_json ?? null;
  const sourceImageId =
    getSummaryString(summaryJson, 'source_image_id') ??
    (position.source_image_id != null && String(position.source_image_id).trim() !== ''
      ? position.source_image_id.trim()
      : null);
  const sourceFileName =
    getSummaryString(summaryJson, 'source_image_original_filename') ??
    (position.source_image_original_filename != null &&
    String(position.source_image_original_filename).trim() !== ''
      ? position.source_image_original_filename.trim()
      : null);

  const primaryProduct =
    products.length > 0 ? mapProductToResultProductInfo(products[0]) : null;

  const entityId = getSummaryString(summaryJson, 'entity_uid');

  return {
    id: position.id,
    sku: position.sku ?? null,
    detectedQty: position.detected_quantity ?? null,
    correctedQty:
      primaryProduct?.correctedQty != null
        ? primaryProduct.correctedQty
        : null,
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
    product: primaryProduct,
    reviewHistory: review_actions.map(mapReviewActionToHistoryItem),
    technicalMetadata: {
      entityId: entityId ?? undefined,
      primaryEvidenceId: position.primary_evidence_id ?? undefined,
      rawStatus: position.status ?? undefined,
    },
  };
}
