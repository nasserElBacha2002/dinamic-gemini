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
  updated_at?: string | null;
}

/** GET /api/v3/inventories — one row with aggregates for list/table screens. */
export interface InventoryListItem extends Inventory {
  aisles_count: number;
  pending_review_count: number;
  last_activity_at: string | null;
}

/**
 * GET /api/v3/inventories — paginated table (Sprint 1.4).
 * Breaking change: the HTTP body is this object, not `InventoryListItem[]`.
 */
export interface PaginatedInventoryListResponse {
  items: InventoryListItem[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

// ─── Inventory visual references (v3.2.4 Phase 2/8) ─────────────────────────

export interface InventoryVisualReference {
  id: string;
  inventory_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  created_at: string;
}

export interface UploadInventoryVisualReferencesResponse {
  items: InventoryVisualReference[];
}

export interface InventoryVisualReferenceListResponse {
  items: InventoryVisualReference[];
}

export interface ReferenceUsageSummary {
  resolved: boolean;
  resolved_count: number;
  provider_consumed: boolean;
  provider_consumed_count: number;
  reference_ids: string[];
  resolution_error?: string | null;
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
  created_at: string;
  updated_at: string;
  error_message?: string | null;
  reference_usage?: ReferenceUsageSummary | null;
  started_at?: string | null;
  finished_at?: string | null;
  last_heartbeat_at?: string | null;
  cancel_requested_at?: string | null;
  current_stage?: string | null;
  current_substep?: string | null;
  current_step_started_at?: string | null;
  attempt_count?: number;
  retry_of_job_id?: string | null;
  failure_code?: string | null;
  failure_message?: string | null;
  execution_id?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
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
  /** Populated on GET .../aisles list (Inventory Detail table). */
  assets_count?: number;
  positions_count?: number;
  pending_review_positions_count?: number;
  last_activity_at?: string | null;
}

/**
 * GET .../inventories/{id}/aisles — paginated (Sprint 1.4).
 * Breaking change: the HTTP body is this object, not `Aisle[]`.
 */
export interface PaginatedAisleListResponse {
  items: Aisle[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

/** GET .../aisles/{aisle_id}/status response. */
export interface AisleStatusResponse {
  aisle: Aisle;
  latest_job: JobSummary | null;
}

export interface ProcessAisleResponse {
  job_id: string;
}

/** GET /api/v3/inventories/processing-provider-options (Phase 5). */
export interface ProcessingModelOption {
  id: string;
  label: string;
}

export interface ProcessingPromptOptionItem {
  key: string;
  label: string;
  description?: string | null;
}

export interface ProcessingProviderOptionItem {
  key: string;
  label: string;
  execution_mode: string;
  description?: string | null;
  models: ProcessingModelOption[];
  default_model?: string | null;
}

export interface ProcessingProviderOptionsResponse {
  default_provider_key: string;
  default_prompt_key: string;
  prompt_profiles: ProcessingPromptOptionItem[];
  providers: ProcessingProviderOptionItem[];
}

export interface JobSummary {
  id: string;
  status: JobStatus | string;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
  reference_usage?: ReferenceUsageSummary | null;
  started_at?: string | null;
  finished_at?: string | null;
  last_heartbeat_at?: string | null;
  cancel_requested_at?: string | null;
  current_stage?: string | null;
  current_substep?: string | null;
  current_step_started_at?: string | null;
  attempt_count?: number;
  retry_of_job_id?: string | null;
  failure_code?: string | null;
  failure_message?: string | null;
  execution_id?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  /** Tracked prompt line (e.g. prompt_key@v2.1); empty if unknown. */
  prompt_version?: string | null;
  /** True when this job is the aisle operational pointer (Phase 6 jobs list). */
  is_operational?: boolean;
}

/** GET .../aisles/{aisle_id}/jobs — newest first (multi-run browsing). */
export interface AisleJobsListResponse {
  operational_job_id?: string | null;
  jobs: JobSummary[];
}

/** Phase 6 — GET .../benchmark/compare (read-only, explicit job pair). */
export interface BenchmarkRunSliceMetrics {
  raw_rows_considered: number;
  consolidated_positions: number;
  total_quantity: number;
  unknown_internal_code_count: number;
  needs_review_count: number;
}

export interface BenchmarkRunCompareSide {
  job_id: string;
  status: string;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  prompt_version?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  metrics: BenchmarkRunSliceMetrics;
}

export interface BenchmarkCompareDiffSummary {
  keys_only_in_a: number;
  keys_only_in_b: number;
  keys_in_both: number;
  quantity_changed: number;
  sku_changed: number;
  position_code_changed: number;
}

export interface BenchmarkCompareDiffRow {
  match_key: string;
  side: string;
  quantity_a?: number | null;
  quantity_b?: number | null;
  sku_a?: string | null;
  sku_b?: string | null;
  position_code_a?: string | null;
  position_code_b?: string | null;
}

export interface AisleBenchmarkCompareResponse {
  inventory_id: string;
  aisle_id: string;
  workflow: string;
  read_only: boolean;
  raw_fetch_truncated: { job_a: boolean; job_b: boolean };
  run_a: BenchmarkRunCompareSide;
  run_b: BenchmarkRunCompareSide;
  diff_summary: BenchmarkCompareDiffSummary;
  diff_rows: BenchmarkCompareDiffRow[];
  diff_rows_truncated: boolean;
}

export interface PromoteOperationalJobResponse {
  aisle_id: string;
  operational_job_id: string;
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

/** v3.2.2+ quantity provenance (legacy flat alias: `qtySource`). */
export type PositionQtySourceV322 =
  | 'detected'
  | 'inferred'
  | 'merge_inferred'
  | 'manual_review'
  | 'label_explicit'
  | 'unknown'
  | 'consolidated';

/** Sprint 2 — canonical product block (prefer over flat `sku`). */
export type PositionProductIdentitySource =
  | 'primary_product'
  | 'summary_technical'
  | 'summary_aggregated';

export interface PositionProductBlock {
  id?: string | null;
  sku?: string | null;
  display_label?: string | null;
  barcode?: string | null;
  identity_source: PositionProductIdentitySource;
}

/** Sprint 2 — canonical quantity; `final` is operator line total (corrected ?? system qty). */
export interface PositionQuantityBlock {
  detected: number;
  corrected?: number | null;
  final: number;
  source: PositionQtySourceV322;
  inference_reason?: string | null;
  resolved?: boolean | null;
}

/** Sprint 2 — canonical traceability (source image vs evidence). */
export interface PositionTraceabilityBlock {
  status?: ApiTraceabilityStatus | string | null;
  source_image_id?: string | null;
  source_image_original_filename?: string | null;
  primary_evidence_id?: string | null;
  has_evidence: boolean;
}

/** Sprint 3 — explicit technical/debug snapshot for detail responses. */
export interface PositionTechnicalSnapshot {
  entity_uid?: string | null;
  entity_type?: string | null;
  internal_code?: string | null;
  review_display_label?: string | null;
  position_barcode?: string | null;
  pallet_id?: string | null;
  count_status?: string | null;
  raw_qty?: number | string | null;
  qty_parse_status?: string | null;
  qty_origin_field?: string | null;
  aggregated_from_ids?: string[] | null;
  audit?: Record<string, unknown> | null;
}

/** Position summary for frontend consumers. `detected_summary_json` is a legacy technical snapshot and is no longer expected from active frontend APIs. */
export interface PositionSummary {
  id: string;
  aisle_id: string;
  status: PositionStatus | string;
  confidence: number;
  needs_review: boolean;
  primary_evidence_id?: string | null;
  created_at: string;
  updated_at: string;
  position_code: string;
  /** @deprecated Legacy raw technical snapshot. Active frontend flows should use `technical_snapshot` instead and not rely on this field. */
  detected_summary_json?: Record<string, unknown> | null;
  /** Sprint 2 — prefer nested blocks when present; flat fields below remain for backward compatibility. */
  product?: PositionProductBlock;
  quantity?: PositionQuantityBlock;
  traceability?: PositionTraceabilityBlock;
  /** @deprecated Prefer `product.sku`. */
  sku?: string | null;
  /** @deprecated Prefer `quantity.detected`. */
  detected_quantity?: number | null;
  /** @deprecated Prefer `quantity.corrected`. */
  corrected_quantity?: number | null;
  /** v3.2.2: system-resolved quantity (not overridden by correction); prefer `quantity.final` for UX line total. */
  /** @deprecated Prefer `quantity.final` for display when corrections exist. */
  qty: number;
  /** Quantity provenance contract (authoritative + merge artifact). */
  /** @deprecated Prefer `quantity.source`. */
  qtySource: PositionQtySourceV322;
  /** v3.2.2: non-null when qtySource='inferred'. */
  /** @deprecated Prefer `quantity.inference_reason`. */
  qtyInferenceReason?: string | null;
  /** v3.2.2: when true/false, qty is from resolved decision; when null, legacy/compatibility path. */
  /** @deprecated Prefer `quantity.resolved`. */
  qtyResolved?: boolean | null;
  /** Epic 3.1.B: optional; when present, summary-level result-to-image traceability for this position. */
  /** @deprecated Prefer `traceability.source_image_id`. */
  source_image_id?: string | null;
  /** Epic 5: optional; original filename of the source image when available (photos jobs). May be absent until the v3 position API is extended to expose it. */
  /** @deprecated Prefer `traceability.source_image_original_filename`. */
  source_image_original_filename?: string | null;
  /** Epic 3.1.B: optional; summary-level traceability status when backend provides it. */
  /** @deprecated Prefer `traceability.status`. */
  traceability_status?: ApiTraceabilityStatus | null;
  /** v3.2.5 Phase 2 Block 4: guaranteed boolean in active v3 contract; backend always sends it. */
  /** @deprecated Prefer `traceability.has_evidence`. */
  has_evidence: boolean;
  /** Multi-run: storage row job id; null = legacy. Used for review drawer / detail `job_id` query. */
  job_id?: string | null;
}

/**
 * GET .../aisles/{aisle_id}/positions — Aisle Results.
 * When `raw_fetch_truncated` is true, do not treat `total_items` / `total_pages` as globally exact
 * for the aisle; they count only consolidated rows from the server’s raw fetch window.
 */
export interface PositionListResponse {
  positions: PositionSummary[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  raw_fetch_truncated: boolean;
  /** Resolved job slice for this response (same semantics as list/detail/merge Phase 2). */
  result_job_id?: string | null;
  /** explicit | operational | legacy */
  result_context_source?: string | null;
}

/** GET /api/v3/review-queue/positions (Sprint 1.4, Sprint 4.2 summary). */
export interface ReviewQueueSummary {
  pending_review: number;
  low_confidence: number;
  invalid_traceability: number;
  qty_zero: number;
  missing_evidence: number;
}

export interface ReviewQueueItem {
  inventory_id: string;
  inventory_name: string;
  aisle_code: string;
  position: PositionSummary;
}

/** Review queue list: filters/sort/pagination + workload summary for KPI band. */
export interface ReviewQueueListResponse {
  summary: ReviewQueueSummary;
  items: ReviewQueueItem[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
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

/** Phase 2 / 5: slice + provider metadata for this row (matches list/merge resolver semantics). */
export interface PositionRunContextSummary {
  job_id?: string | null;
  result_context_source: string;
  resolved_job_id?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  prompt_version?: string | null;
}

/** Response for GET .../aisles/{aisle_id}/positions/{position_id}. v3.1.1: Result-centric; products are not returned. Backend always sends review_actions (array). */
export interface PositionDetailResponse {
  position: PositionSummary;
  technical_snapshot?: PositionTechnicalSnapshot | null;
  evidences: EvidenceSummary[];
  /** Review audit history — Épica 8. v3.2.5 Phase 8: required; backend sends list (default_factory=list). */
  review_actions: ReviewActionSummary[];
  run_context: PositionRunContextSummary;
}

export interface RunMergeResponse {
  operation_mode: string;
  authoritative_quantity_updated: boolean;
  raw_count: number;
  normalized_count: number;
  final_count: number;
  product_records_updated: number;
}

export interface MergeResultItemResponse {
  id: string;
  position_id?: string | null;
  sku?: string | null;
  product_name?: string | null;
  merged_quantity: number;
  normalized_label_ids: string[];
  review_required: boolean;
  explanation_summary?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MergeResultsResponse {
  results: MergeResultItemResponse[];
}

// v1 job-entities types (TraceabilitySummary, JobEntityListItem, JobEntitiesListResponse) removed in Stage 3;
// the only supported surface is v3 positions (Result). ApiTraceabilityStatus remains in shared.ts for position/result UI.
