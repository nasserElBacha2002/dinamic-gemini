/**
 * API response DTOs and entity shapes returned by the backend.
 * These types represent raw response contracts; the same shapes are used by the UI.
 */

import type {
  InventoryStatus,
  AisleStatus,
  JobStatus,
  PositionStatus,
  EvidenceType,
  ReviewActionType,
  ApiTraceabilityStatus,
} from './shared';

// ─── Inventory ─────────────────────────────────────────────────────────────

export interface Inventory {
  id: string;
  name: string;
  status: InventoryStatus | string;
  created_at?: string | null;
}

/** GET /api/v3/inventories/{inventory_id}/metrics response — Épica 9 (§9.6). */
export interface InventoryMetrics {
  total_positions: number;
  total_reviewed_positions: number;
  auto_accepted_positions: number;
  corrected_positions: number;
  deleted_positions: number;
  success_rate: number;
  correction_rate: number;
  deletion_rate: number;
}

// ─── Aisle ─────────────────────────────────────────────────────────────────

export interface AisleJobSummary {
  id: string;
  status: JobStatus | string;
  updated_at: string;
  error_message?: string | null;
}

export interface Aisle {
  id: string;
  inventory_id: string;
  code: string;
  status: AisleStatus | string;
  created_at: string;
  updated_at: string;
  error_code?: string | null;
  error_message?: string | null;
  latest_job?: AisleJobSummary | null;
}

/** GET .../aisles/{aisle_id}/status response. */
export interface AisleStatusResponse {
  aisle: Aisle;
  latest_job: JobSummary | null;
}

export interface ProcessAisleResponse {
  job_id: string;
}

export interface JobSummary {
  id: string;
  status: JobStatus | string;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
}

/** Single execution log event (v3.1.1). */
export interface ExecutionLogEvent {
  ts: string;
  stage: string;
  level: string;
  message: string;
  payload?: Record<string, unknown> | null;
}

/** GET .../aisles/{aisle_id}/jobs/{job_id}/execution-log response. */
export interface ExecutionLogResponse {
  events: ExecutionLogEvent[];
}

/** Source asset (photo/video) for an aisle — Épica 4. */
export interface SourceAssetSummary {
  id: string;
  aisle_id: string;
  type: 'photo' | 'video';
  original_filename: string;
  /** Backend storage path; not used by current UI (reserved for future evidence/media views). */
  storage_path: string;
  mime_type: string;
  uploaded_at: string;
}

/** Response for POST .../aisles/{aisle_id}/assets. */
export interface UploadAisleAssetsResponse {
  assets: SourceAssetSummary[];
}

// ─── Position / result ─────────────────────────────────────────────────────

/**
 * For the visible review model (v3.1.1+), prefer ResultSummary / ResultDetail and
 * mappers from features/results. These API types remain the raw contract for the
 * positions endpoints.
 */

/** Position summary for list responses. Prefer optional sku and detected_quantity when present; detected_summary_json is retained for backward compatibility. */
export interface PositionSummary {
  id: string;
  aisle_id: string;
  status: PositionStatus | string;
  confidence: number;
  needs_review: boolean;
  primary_evidence_id?: string | null;
  created_at: string;
  updated_at: string;
  detected_summary_json?: Record<string, unknown> | null;
  sku?: string | null;
  detected_quantity?: number | null;
  corrected_quantity?: number | null;
  /** Epic 3.1.B: optional; when present, summary-level result-to-image traceability for this position. */
  source_image_id?: string | null;
  /** Epic 5: optional; original filename of the source image when available (photos jobs). May be absent until the v3 position API is extended to expose it. */
  source_image_original_filename?: string | null;
  /** Epic 3.1.B: optional; summary-level traceability status when backend provides it. */
  traceability_status?: ApiTraceabilityStatus | null;
  /** Epic 2: explicit flag when backend sends it; frontend may derive from primary_evidence_id when absent. */
  has_evidence?: boolean;
}

/** Response for GET .../aisles/{aisle_id}/positions. */
export interface PositionListResponse {
  positions: PositionSummary[];
}

/** Product record within a position. */
export interface ProductRecordSummary {
  id: string;
  position_id: string;
  sku: string;
  description?: string | null;
  detected_quantity: number;
  corrected_quantity?: number | null;
  confidence: number;
  created_at: string;
  updated_at: string;
}

/** Evidence (crop/media) for a position. */
export interface EvidenceSummary {
  id: string;
  entity_type: string;
  entity_id: string;
  type: EvidenceType | string;
  storage_path: string;
  /** Backend may return null when evidence is not linked to a source asset. */
  source_asset_id?: string | null;
  is_primary: boolean;
  frame_index?: number | null;
  timestamp_ms?: number | null;
  bbox_json?: Record<string, unknown> | null;
  quality_score?: number | null;
}

/** Single review action in audit history — Épica 8. */
export interface ReviewActionSummary {
  id: string;
  position_id: string;
  action_type: ReviewActionType;
  before_json: Record<string, unknown>;
  after_json: Record<string, unknown>;
  created_at: string;
  user_id?: string | null;
  comment?: string | null;
}

/** Response for GET .../aisles/{aisle_id}/positions/{position_id}. v3.1.1: Result-centric; products are not returned. */
export interface PositionDetailResponse {
  position: PositionSummary;
  evidences: EvidenceSummary[];
  /** Review audit history — Épica 8. */
  review_actions?: ReviewActionSummary[];
}

// ─── v1 Job entities (Epic 3.1.B / 3.1.C) ───────────────────────────────────────────

/** Epic 3.1.C — Job-level traceability counts (full job, not filtered subset). */
export interface TraceabilitySummary {
  total_entities: number;
  valid: number;
  missing: number;
  invalid: number;
  unvalidated: number;
}

/**
 * Single entity in GET /api/v1/inventory/jobs/{job_id}/entities response.
 * @deprecated v3.1.1 — For the main review flow use Result (positions) and features/results types.
 * This list remains for job-level traceability views; it is no longer the primary visible model.
 */
export interface JobEntityListItem {
  entity_uid: string;
  pallet_id?: string | null;
  entity_type: string;
  count_status?: string | null;
  entity_quality_score?: number | null;
  evidence_ref?: string | null;
  /** Epic 3.1.B: image_id of source image for this entity. */
  source_image_id?: string | null;
  /** Epic 5: original filename of the source image when available (photos jobs; human-readable). */
  source_image_original_filename?: string | null;
  /** Epic 3.1.B: valid | missing | invalid | unvalidated. */
  traceability_status?: ApiTraceabilityStatus | null;
  /** Epic 3.1.B: diagnostic only (e.g. reason when status is invalid). */
  traceability_warning?: string | null;
  /** Epic 3.1.D / Epic 4: review-oriented display label (prefers product/SKU, fallback position/pallet). Not guaranteed product-only. */
  review_display_label?: string | null;
  /** Epic 3.1.D: deprecated alias, same value as review_display_label. Kept for backward compatibility. */
  product_display_label?: string | null;
}

/** Response for GET /api/v1/inventory/jobs/{job_id}/entities. Epic 3.1.C: optional traceability_summary (full-job counts).
 * @deprecated v3.1.1 — Primary review flow uses positions (Result); use features/results for the visible model. */
export interface JobEntitiesListResponse {
  entities: JobEntityListItem[];
  /** When present, always full-job summary regardless of filter. Omitted for legacy reports. */
  traceability_summary?: TraceabilitySummary | null;
}
