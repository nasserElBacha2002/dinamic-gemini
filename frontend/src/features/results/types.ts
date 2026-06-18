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

/** Phase 4.8 — structural evidence traceability (includes legacy / artifact unavailable). */
export type EvidenceTraceabilityStatus =
  | 'valid'
  | 'invalid'
  | 'missing'
  | 'unvalidated'
  | 'legacy_unavailable'
  | 'artifact_unavailable';

export type EvidenceSourceKind =
  | 'structural_result_evidence'
  | 'legacy_json'
  | 'unavailable';

export type ImageAccessStatus = 'available' | 'url_unavailable' | 'not_allowed';

/** Phase 4.8 — durable traceability_manifest metadata (safe subset). */
export interface TraceabilityArtifactMetadata {
  kind: string;
  published: boolean;
  required: boolean;
  status: string;
  storageKey?: string | null;
  contentHash?: string | null;
  sizeBytes?: number | null;
  publishedAt?: string | null;
}

/** Phase 4.8 — mapped from API ResultEvidenceViewResponse. */
export interface ResultEvidenceView {
  displayable: boolean;
  traceabilityStatus: EvidenceTraceabilityStatus | string;
  traceabilityWarning?: string | null;
  role?: string | null;
  sourceImageId?: string | null;
  sourceAssetId?: string | null;
  resolvedManifestEntryId?: string | null;
  rawManifestEntryId?: string | null;
  rawSourceImageId?: string | null;
  imageUrl?: string | null;
  thumbnailUrl?: string | null;
  imageAccessStatus?: ImageAccessStatus | string | null;
  sourceKind: EvidenceSourceKind | string;
  provider?: string | null;
  modelName?: string | null;
}

/** Review status for the visible result (maps from position status + needs_review). */
export type ReviewStatus =
  | 'DETECTED'
  | 'CONFIRMED'
  | 'NEEDS_REVIEW'
  | 'IMAGE_MISMATCH'
  | 'MISSING'
  | 'INVALID'
  | 'NOT_COUNTABLE';

/** Summary row for the results list (table). */
export interface ResultSummary {
  id: string;
  sku: string | null;
  positionCode: string | null;
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
    | 'consolidated'
    | null;
  qtyResolved?: boolean | null;
  qtyInferenceReason?: string | null;
  confidence: number | null;
  reviewStatus: ReviewStatus;
  traceabilityStatus: TraceabilityStatus;
  needsReview: boolean;
  updatedAt: string;
  /** Crop row exists (primary_evidence_id); not the same as validated display evidence. */
  hasEvidence: boolean;
  /** Phase 4.2: true only when traceability is VALID and backend confirms display eligibility. */
  hasValidEvidence: boolean;
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
  positionCode: string | null;
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
    | 'consolidated'
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
  /** Phase 4.2: validated display eligibility from API traceability.has_valid_evidence. */
  hasValidEvidence: boolean;
  /** Phase 4.8: structural evidence contract from detail API (authoritative when present). */
  evidenceView?: ResultEvidenceView | null;
  /** Phase 4.8: durable traceability_manifest metadata for resolved job context. */
  traceabilityArtifact?: TraceabilityArtifactMetadata | null;
  /** Operational diagnostic from API (may be shown in technical/expandable UI). */
  traceabilityWarning?: string | null;
  evidence: ResultEvidence[];
  reviewHistory: ReviewHistoryItem[];
  technicalMetadata?: {
    entityId?: string | null;
    primaryEvidenceId?: string | null;
    rawStatus?: string | null;
  };
  /** Storage row ``positions.job_id`` for POST .../reviews ``job_id`` only (null/omit = legacy). */
  storageJobId?: string | null;
  /** Read-path slice hints from API run_context — not used for review writes. */
  runContextJobId?: string | null;
  runContextResolvedJobId?: string | null;
}
