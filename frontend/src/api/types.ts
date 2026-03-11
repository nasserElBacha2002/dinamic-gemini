/**
 * v3 API DTOs and error type — aligned with backend schemas.
 */

export const INVENTORY_STATUSES = [
  'draft',
  'processing',
  'in_review',
  'completed',
  'failed',
] as const;
export type InventoryStatus = (typeof INVENTORY_STATUSES)[number];

export const AISLE_STATUSES = [
  'created',
  'assets_uploaded',
  'queued',
  'processing',
  'processed',
  'in_review',
  'completed',
  'failed',
] as const;
export type AisleStatus = (typeof AISLE_STATUSES)[number];

/** Backend job status values (v3 API). */
export const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

/** Backend position status values (result model — Épica 6). */
export const POSITION_STATUSES = ['detected', 'reviewed', 'corrected', 'deleted'] as const;
export type PositionStatus = (typeof POSITION_STATUSES)[number];

/** Backend evidence type values (result model — Épica 6). */
export const EVIDENCE_TYPES = [
  'original_image',
  'video_frame',
  'position_crop',
  'product_crop',
  'label_crop',
  'annotated_image',
] as const;
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

export interface Inventory {
  id: string;
  name: string;
  status: InventoryStatus | string;
  created_at?: string | null;
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

export interface AisleJobSummary {
  id: string;
  status: JobStatus | string;
  updated_at: string;
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

export interface CreateInventoryRequest {
  name: string;
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

export interface CreateAisleRequest {
  code: string;
}

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

/** Backend review action type values. */
export const REVIEW_ACTION_TYPES = ['confirm', 'update_quantity', 'update_sku', 'delete_position'] as const;
export type ReviewActionType = (typeof REVIEW_ACTION_TYPES)[number];

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

/** Request body for POST .../positions/{position_id}/reviews. */
export interface ReviewActionRequest {
  action_type: ReviewActionType;
  product_id?: string | null;
  corrected_quantity?: number | null;
  sku?: string | null;
  description?: string | null;
}

/** Response for GET .../aisles/{aisle_id}/positions/{position_id}. */
export interface PositionDetailResponse {
  position: PositionSummary;
  products: ProductRecordSummary[];
  evidences: EvidenceSummary[];
  /** Review audit history — Épica 8. */
  review_actions?: ReviewActionSummary[];
}

export interface ApiErrorDetail {
  detail?: string | unknown;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly data?: ApiErrorDetail
  ) {
    super(message);
    this.name = 'ApiError';
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}
