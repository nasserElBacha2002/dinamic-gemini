/**
 * v3.1.1 — Result-centric visible review model (Epic 1).
 *
 * These types define the primary frontend-visible contract for the review flow.
 * Prefer these over raw API Position/Entity types when building UI.
 *
 * Result is the single operational unit: SKU, detected quantity, traceability,
 * evidence, and review actions. Entity remains an internal/backend concept.
 */

/** Traceability status for display (uppercase, aligned with backend valid | missing | invalid | unvalidated). */
export type TraceabilityStatus =
  | 'VALID'
  | 'MISSING'
  | 'INVALID'
  | 'UNVALIDATED';

/** Review status for the visible result (maps from position status + needs_review). */
export type ReviewStatus =
  | 'DETECTED'
  | 'CONFIRMED'
  | 'NEEDS_REVIEW'
  | 'MISSING'
  | 'INVALID'
  | 'NOT_COUNTABLE';

/** Summary row for the results list (table). */
export interface ResultSummary {
  id: string;
  sku: string | null;
  detectedQty: number | null;
  confidence: number | null;
  reviewStatus: ReviewStatus;
  traceabilityStatus: TraceabilityStatus;
  needsReview: boolean;
  updatedAt: string;
  hasEvidence: boolean;
}

/** Single evidence item (image/crop) for a result. */
export interface ResultEvidence {
  id: string;
  role: 'PRIMARY' | 'SUPPORTING';
  sourceImageId: string | null;
  sourceFileName: string | null;
  imageUrl: string | null;
  thumbnailUrl?: string | null;
}

/** Product info block in result detail (from product record). */
export interface ResultProductInfo {
  productId: string | null;
  sku: string | null;
  description?: string | null;
  correctedQty?: number | null;
}

/** One review history entry (audit). */
export interface ReviewHistoryItem {
  id: string;
  action: string;
  createdAt: string;
  userName?: string | null;
  notes?: string | null;
}

/** Full result detail (detail screen). */
export interface ResultDetail {
  id: string;
  sku: string | null;
  detectedQty: number | null;
  correctedQty: number | null;
  confidence: number | null;
  reviewStatus: ReviewStatus;
  traceabilityStatus: TraceabilityStatus;
  needsReview: boolean;
  updatedAt: string;
  sourceImageId: string | null;
  sourceFileName: string | null;
  evidence: ResultEvidence[];
  product: ResultProductInfo | null;
  reviewHistory: ReviewHistoryItem[];
  technicalMetadata?: {
    entityId?: string | null;
    primaryEvidenceId?: string | null;
    rawStatus?: string | null;
  };
}
