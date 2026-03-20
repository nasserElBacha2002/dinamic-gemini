/**
 * v3.1.1 — Result-centric visible review model (Epic 1).
 *
 * Type definitions only. No runtime code, no React/MUI, no components.
 * Use these types when building or refactoring the results list and result detail UI.
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
  /** v3.2.2: corrected_quantity from backend (may be null). */
  correctedQty: number | null;
  /** v3.2.2: resolved qty = corrected_quantity ?? qty (backend contract). */
  resolvedQty: number | null;
  /** v3.2.2: provenance of resolved qty. */
  qtySource?:
    | 'detected'
    | 'inferred'
    | 'merge_inferred'
    | 'manual_review'
    | 'label_explicit'
    | 'unknown'
    | null;
  qtyResolved?: boolean | null;
  qtyInferenceReason?: string | null;
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

/** One review history entry (audit). Phase 6: before/after for human-readable change summary. */
export interface ReviewHistoryItem {
  id: string;
  action: string;
  createdAt: string;
  userName?: string | null;
  notes?: string | null;
  /** Raw before/after from API; used to build concise change summary. */
  beforeJson?: Record<string, unknown> | null;
  afterJson?: Record<string, unknown> | null;
}

/** Full result detail (detail screen). */
export interface ResultDetail {
  id: string;
  sku: string | null;
  detectedQty: number | null;
  correctedQty: number | null;
  /** v3.2.2: resolved qty = corrected_quantity ?? qty (backend contract). */
  resolvedQty: number | null;
  /** v3.2.5 Phase 6: system-resolved qty (backend qty) for display when corrected_quantity is set. Mapper always sets this (position.qty ?? null). */
  systemQty: number | null;
  qtySource?:
    | 'detected'
    | 'inferred'
    | 'merge_inferred'
    | 'manual_review'
    | 'label_explicit'
    | 'unknown'
    | null;
  qtyResolved?: boolean | null;
  qtyInferenceReason?: string | null;
  confidence: number | null;
  reviewStatus: ReviewStatus;
  traceabilityStatus: TraceabilityStatus;
  needsReview: boolean;
  updatedAt: string;
  sourceImageId: string | null;
  sourceFileName: string | null;
  evidence: ResultEvidence[];
  reviewHistory: ReviewHistoryItem[];
  technicalMetadata?: {
    entityId?: string | null;
    primaryEvidenceId?: string | null;
    rawStatus?: string | null;
  };
}
