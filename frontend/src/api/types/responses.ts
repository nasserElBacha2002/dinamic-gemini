/**
 * API response DTOs and entity shapes returned by the backend.
 * These types represent raw response contracts; the same shapes are used by the UI.
 */

import type {
  ClientStatus,
  ClientSupplierStatus,
  InventoryStatus,
  InventoryProcessingMode,
  AisleIdentificationMode,
  AisleIdentificationModeSource,
  AisleIdentificationExecutionStrategy,
  AisleStatus,
  JobStatus,
  FinalizationStatus,
  FinalizationStep,
  PositionStatus,
  EvidenceType,
  ReviewActionType,
  ApiTraceabilityStatus,
} from './shared';

// ─── Clients ───────────────────────────────────────────────────────────────

export interface Client {
  id: string;
  name: string;
  status: ClientStatus | string;
  created_at: string;
  updated_at: string;
  identification_mode?: AisleIdentificationMode | string | null;
  effective_identification_mode?: AisleIdentificationMode | string;
  identification_mode_source?: AisleIdentificationModeSource | string;
}

export interface ClientsListResponse {
  items: Client[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface ClientSupplier {
  id: string;
  client_id: string;
  name: string;
  status: ClientSupplierStatus | string;
  created_at: string;
  updated_at: string;
}

export interface ClientSuppliersListResponse {
  items: ClientSupplier[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

/** Supplier-scoped reference images (Phase C — not used by CV pipeline until explicitly wired). */
export interface SupplierReferenceImage {
  id: string;
  client_supplier_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  content_type?: string | null;
  file_size_bytes?: number | null;
  label?: string | null;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierReferenceImagesListResponse {
  items: SupplierReferenceImage[];
}

export interface UploadSupplierReferenceImagesResponse {
  items: SupplierReferenceImage[];
}

export interface DeleteSupplierReferenceImageResponse {
  deleted: boolean;
  id: string;
}

export interface SupplierPromptConfig {
  id: string;
  client_supplier_id: string;
  provider_name?: string | null;
  model_name?: string | null;
  instructions_text: string;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SupplierPromptConfigsListResponse {
  items: SupplierPromptConfig[];
}

// ─── Inventory ─────────────────────────────────────────────────────────────

export interface PrimaryExecutionConfig {
  provider_name: string;
  model_name: string;
  prompt_key: string;
  prompt_version?: string | null;
}

export interface Inventory {
  id: string;
  name: string;
  client_id?: string | null;
  status: InventoryStatus | string;
  processing_mode?: InventoryProcessingMode | string;
  primary_execution_config?: PrimaryExecutionConfig | null;
  created_at?: string | null;
  updated_at?: string | null;
  identification_mode?: AisleIdentificationMode | string | null;
  effective_identification_mode?: AisleIdentificationMode | string;
  identification_mode_source?: AisleIdentificationModeSource | string;
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
  finalization_status?: FinalizationStatus | string | null;
  current_finalization_step?: FinalizationStep | string | null;
  last_completed_finalization_step?: string | null;
  finalization_error_code?: string | null;
}

export interface Aisle {
  id: string;
  inventory_id: string;
  client_supplier_id?: string | null;
  code: string;
  status: AisleStatus | string;
  /**
   * Soft-active flag from API. Treat missing as active for backward compatibility
   * (older payloads / cached rows without the field).
   */
  is_active?: boolean;
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
  identification_mode?: AisleIdentificationMode | string | null;
  effective_identification_mode?: AisleIdentificationMode | string;
  identification_mode_source?: AisleIdentificationModeSource | string;
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
  identification_mode?: AisleIdentificationMode | string | null;
  identification_mode_source?: AisleIdentificationModeSource | string | null;
  execution_strategy?: AisleIdentificationExecutionStrategy | string | null;
  configuration_snapshot_version?: number | null;
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
  production_available?: boolean | null;
  unavailable_reason?: string | null;
  is_default_provider?: boolean;
}

export interface ProcessingProviderOptionsResponse {
  mode?: 'test' | 'production';
  default_provider_key: string;
  default_model_key?: string | null;
  default_prompt_key: string;
  prompt_profiles: ProcessingPromptOptionItem[];
  providers: ProcessingProviderOptionItem[];
}

/** GET /api/v3/admin/ai-config — operational inspection only (username `admin`). */
export interface AdminAiConfigServerDefaults {
  llm_provider: string;
  hybrid_prompt_key: string;
  prompt_version?: string | null;
}

export interface AdminAiConfigModelItem {
  id: string;
  label: string;
  is_default: boolean;
}

export interface AdminAiConfigProviderCapabilities {
  is_default_pipeline_provider: boolean;
  credential_configured: boolean;
  multimodal_aisle_analysis_supported: boolean;
  execution_mode: string;
}

export interface AdminAiConfigProviderInstructions {
  provider_specific_note: string;
}

export interface AdminAiConfigResponseContract {
  expects_json: boolean;
  wire_transport: string;
  validation_function: string;
  normalization_function: string;
  normalization_family: string;
  alias_promotion_policy: string;
  claude_product_label_to_internal_code_when_valid: boolean;
  required_root_keys: string[];
  extra_root_keys_policy_short: string;
  required_entity_keys: string[];
  canonical_entity_keys: string[];
  nullable_optional_entity_keys: string[];
  canonical_example_json: string;
  transport_notes: string[];
}

export interface AdminAiConfigComposition {
  hybrid_base_mode: string;
  parity_mode_affects_prompt_assembly: boolean;
  multimodal_context_policy: string;
}

export interface AdminAiConfigPromptCatalogItem {
  key: string;
  label: string;
  description?: string | null;
}

export interface AdminAiConfigPromptVariantSummary {
  prompt_key: string;
  pipeline_provider_key: string;
  prompt_parity_mode: boolean;
  variant_label: string;
}

export interface AdminAiComposedPromptResponse {
  prompt_key: string;
  pipeline_provider_key: string;
  prompt_parity_mode: boolean;
  variant_label: string;
  composed_prompt_text: string;
}

export interface AdminAiConfigProviderDetail {
  key: string;
  label: string;
  description?: string | null;
  execution_mode: string;
  models: AdminAiConfigModelItem[];
  default_model?: string | null;
  capabilities: AdminAiConfigProviderCapabilities;
  instructions: AdminAiConfigProviderInstructions;
  response_contract: AdminAiConfigResponseContract;
  composition: AdminAiConfigComposition;
  prompt_variant_summaries: AdminAiConfigPromptVariantSummary[];
}

export interface AdminAiConfigResponse {
  generated_at: string;
  server_defaults: AdminAiConfigServerDefaults;
  providers: AdminAiConfigProviderDetail[];
  prompt_catalog: AdminAiConfigPromptCatalogItem[];
  global_instructions_note: string;
}

// ─── Jobs / finalization ───────────────────────────────────────────────────

export interface FinalizationStageAssessment {
  stage: string;
  status: string;
  evidence_level: string;
  completed_at?: string | null;
  verification_required: boolean;
  last_error_code?: string | null;
}

export interface FinalizationAssessment {
  outcome: string;
  technical_result_status: string;
  finalization_status: string;
  last_confirmed_stage?: string | null;
  next_required_stage?: string | null;
  recovery_candidate: boolean;
  blocking_reason?: string | null;
  stages: Record<string, FinalizationStageAssessment>;
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
  identification_mode?: AisleIdentificationMode | string | null;
  identification_mode_source?: AisleIdentificationModeSource | string | null;
  execution_strategy?: AisleIdentificationExecutionStrategy | string | null;
  configuration_snapshot_version?: number | null;
  finalization_status?: FinalizationStatus | string | null;
  current_finalization_step?: FinalizationStep | string | null;
  last_completed_finalization_step?: string | null;
  finalization_error_code?: string | null;
  finalization_error_metadata?: Record<string, unknown> | null;
  finalization_started_at?: string | null;
  finalization_completed_at?: string | null;
  domain_persisted_at?: string | null;
  artifacts_published_at?: string | null;
  finalization_assessment?: FinalizationAssessment | null;
  /** True when this job is the aisle operational pointer (Phase 6 jobs list). */
  is_operational?: boolean;
  /** Present when ``result_json`` includes a validated LLM cost snapshot (list jobs; additive). */
  llm_cost_snapshot?: LlmCostSnapshot | null;
  /** Phase 2 additive per-asset progress when orchestrator ran. */
  asset_progress?: AssetProgress | null;
}

export interface AssetProgress {
  total: number;
  pending: number;
  processing: number;
  resolved: number;
  unrecognized: number;
  failed: number;
  manual_review: number;
  cancelled: number;
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

export interface LlmUsageSnapshot {
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cached_input_tokens?: number | null;
  cache_write_tokens?: number | null;
  thinking_tokens?: number | null;
  tool_requests?: number | null;
  image_input_count?: number | null;
  image_input_tokens?: number | null;
  audio_input_tokens?: number | null;
  video_input_tokens?: number | null;
}

export interface LlmPricingSnapshot {
  pricing_source?: string | null;
  pricing_version?: string | null;
  captured_at?: string | null;
  pricing_catalog_entry_captured_at?: string | null;
  billing_currency?: string | null;
  price_units?: string | null;
  provider?: string | null;
  model?: string | null;
  canonical_model?: string | null;
  input_cost_per_million?: string | null;
  output_cost_per_million?: string | null;
  cached_input_cost_per_million?: string | null;
  thinking_cost_per_million?: string | null;
  cache_write_cost_per_million?: string | null;
  tool_request_unit_cost?: string | null;
  image_input_unit_cost?: string | null;
  audio_input_cost_per_million?: string | null;
  video_input_cost_per_million?: string | null;
  thinking_cost_rule?: string | null;
  thinking_billed_as?: string | null;
  /** operator_approved | embedded_placeholder | unknown — from backend pricing_snapshot */
  pricing_confidence?: string | null;
}

export interface LlmComputedCost {
  subtotal_input?: string | null;
  subtotal_output?: string | null;
  subtotal_cached?: string | null;
  subtotal_cache_write?: string | null;
  subtotal_thinking?: string | null;
  subtotal_tools?: string | null;
  subtotal_image?: string | null;
  subtotal_audio?: string | null;
  subtotal_video?: string | null;
  /** Sum of priced dimensions when ``capture_status`` is ``partial``. */
  partial_total_cost?: string | null;
  total_cost?: string | null;
  currency?: string | null;
  /** Machine-readable when total_cost is null (e.g. pricing_entry_missing). */
  total_cost_unavailable_reason?: string | null;
}

export interface LlmCostSnapshot {
  provider: string;
  model?: string | null;
  canonical_model?: string | null;
  /** True when a catalog row matched provider+model (pricing_snapshot may still have null rates). */
  pricing_available?: boolean | null;
  billing_currency?: string | null;
  usage: LlmUsageSnapshot;
  pricing_snapshot: LlmPricingSnapshot;
  computed_cost: LlmComputedCost;
  capture_status: 'exact' | 'estimated' | 'partial' | 'unavailable' | string;
  capture_notes?: string[];
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
  /** Wall-clock ``finished_at - started_at`` when both timestamps exist and coherent. */
  execution_time_seconds?: number | null;
  /** Compact duration (e.g. `12.4s`); null when duration unknown. */
  execution_time_human?: string | null;
  metrics: BenchmarkRunSliceMetrics;
  llm_cost_snapshot?: LlmCostSnapshot | null;
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

export interface BenchmarkCompareManyDelta {
  total_quantity_diff: number;
  consolidated_positions_diff: number;
  unknown_internal_code_diff: number;
  needs_review_diff: number;
  /** Target wall time minus baseline (seconds); null if either duration unknown. */
  execution_time_delta?: number | null;
}

export interface BenchmarkCompareManySummary {
  job_count: number;
  baseline_job_id: string;
  max_total_quantity: number;
  min_total_quantity: number;
  max_needs_review: number;
  min_needs_review: number;
  max_consolidated_positions: number;
  min_consolidated_positions: number;
  max_unknown_internal_code_count: number;
  min_unknown_internal_code_count: number;
  /** Present only when every selected job has ``execution_time_seconds``. */
  min_execution_time_seconds?: number | null;
  max_execution_time_seconds?: number | null;
}

export interface BenchmarkCompareManyRawFetchFlag {
  job_id: string;
  truncated: boolean;
}

export interface BenchmarkCompareManyDiff {
  baseline_job_id: string;
  target_job_id: string;
  diff_summary: BenchmarkCompareDiffSummary;
  delta: BenchmarkCompareManyDelta;
  diff_rows: BenchmarkCompareDiffRow[];
  diff_rows_truncated: boolean;
}

export interface AisleBenchmarkCompareManyResponse {
  inventory_id: string;
  aisle_id: string;
  workflow: string;
  read_only: boolean;
  baseline_job_id: string;
  jobs: BenchmarkRunCompareSide[];
  comparisons: BenchmarkCompareManyDiff[];
  summary: BenchmarkCompareManySummary;
  raw_fetch_truncated: BenchmarkCompareManyRawFetchFlag[];
}

export interface PromoteOperationalJobResponse {
  aisle_id: string;
  operational_job_id: string;
}

/** GET .../jobs/{job_id}/auditability — Phase H read model (snake_case matches backend `to_jsonable`). */
export interface RunAuditMetadataSources {
  job_row: boolean;
  result_json: boolean;
  aisle_join: boolean;
  inventory_join: boolean;
  hybrid_report: boolean;
  execution_log: boolean;
  run_audit_snapshot: boolean;
}

export interface RunAuditReferenceUsage {
  resolved: boolean;
  resolved_count: number;
  provider_consumed: boolean;
  provider_consumed_count: number;
  reference_ids: string[];
  resolution_error: string | null;
}

export interface RunAuditabilityView {
  job_id: string;
  status: string;
  target_type: string;
  target_id: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;

  inventory_id: string | null;
  aisle_id: string | null;
  client_id: string | null;
  client_supplier_id: string | null;

  provider_name: string | null;
  model_name: string | null;
  prompt_key: string | null;
  prompt_version: string | null;

  supplier_prompt_config_id: string | null;
  supplier_prompt_config_version: string | null;
  supplier_prompt_fallback_used: boolean | null;
  supplier_prompt_fallback_reason: string | null;

  protected_prompt_contract_key: string | null;
  protected_prompt_contract_version: string | null;
  effective_prompt_hash: string | null;
  prompt_composition_available: boolean;

  reference_usage: RunAuditReferenceUsage | null;
  supplier_reference_images_used: boolean | null;
  inventory_visual_references_used: boolean | null;
  reference_source: string | null;
  reference_image_count: number | null;
  reference_ids: string[];

  warnings: string[];

  metadata_sources: RunAuditMetadataSources;
  missing_metadata: string[];
  legacy_mode: boolean;
  /** Validated LLM cost snapshot from ``result_json.llm_cost_snapshot`` (Phase H5). */
  cost_snapshot?: LlmCostSnapshot | null;
}

/** GET /api/v3/observability/metrics — Phase H5 (snake_case matches backend). */
export interface ObservabilityMetricsRange {
  from: string;
  to: string;
}

export interface ObservabilityMetricsFiltersState {
  client_id: string | null;
  client_supplier_id: string | null;
  provider_name: string | null;
  model_name: string | null;
}

export interface ObservabilityMetricsTotals {
  runs_total: number;
  runs_succeeded: number;
  runs_failed: number;
  success_rate: number | null;
  failure_rate: number | null;
  fallback_runs: number;
  missing_prompt_config_runs: number;
  missing_reference_runs: number;
  legacy_runs: number;
}

export interface ObservabilityMetricsByClientRow {
  client_id: string | null;
  runs_total: number;
  runs_succeeded: number;
  runs_failed: number;
  failure_rate: number | null;
}

export interface ObservabilityMetricsBySupplierRow {
  client_supplier_id: string | null;
  client_id: string | null;
  runs_total: number;
  runs_succeeded: number;
  runs_failed: number;
  fallback_runs: number;
  missing_reference_runs: number;
  failure_rate: number | null;
}

export interface ObservabilityMetricsByProviderModelRow {
  provider_name: string | null;
  model_name: string | null;
  runs_total: number;
  runs_succeeded: number;
  runs_failed: number;
  failure_rate: number | null;
}

export interface ObservabilityMetricsDataQuality {
  jobs_with_audit_snapshot: number;
  jobs_without_audit_snapshot: number;
  jobs_with_missing_metadata: number;
  artifact_dependent_jobs: number;
}

export interface ObservabilityMetricsResponse {
  range: ObservabilityMetricsRange;
  filters: ObservabilityMetricsFiltersState;
  totals: ObservabilityMetricsTotals;
  by_client: ObservabilityMetricsByClientRow[];
  by_supplier: ObservabilityMetricsBySupplierRow[];
  by_provider_model: ObservabilityMetricsByProviderModelRow[];
  data_quality: ObservabilityMetricsDataQuality;
}

/** Single execution log event (raw row + derived metadata for filters / export). */
export interface ExecutionLogEvent {
  ts: string;
  stage: string;
  level: string;
  message: string;
  payload?: unknown;
  event_job_id?: string | null;
  event_attempt?: number | null;
  event_execution_id?: string | null;
  is_requested_job_event?: boolean;
}

/** GET .../aisles/{aisle_id}/jobs/{job_id}/execution-log — enriched envelope. */
export interface ExecutionLogResponse {
  inventory_id: string;
  aisle_id: string;
  requested_job_id: string;
  available_job_ids: string[];
  available_attempts: number[];
  available_execution_ids: string[];
  events: ExecutionLogEvent[];
}

export type ArtifactCategory = 'INPUT' | 'INTERMEDIATE' | 'OUTPUT' | 'LOG' | 'DEBUG' | 'EXPORT';
export type ArtifactAvailabilityStatus =
  | 'PENDING'
  | 'AVAILABLE'
  | 'PUBLISH_FAILED'
  | 'MISSING'
  | 'EXPIRED'
  | 'DELETED'
  | 'CORRUPTED';

export interface JobArtifact {
  id: string;
  job_id: string;
  category: ArtifactCategory | string;
  kind: string;
  stage?: string | null;
  display_name: string;
  original_filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  checksum?: string | null;
  width?: number | null;
  height?: number | null;
  status: ArtifactAvailabilityStatus | string;
  is_current: boolean;
  is_previewable: boolean;
  is_downloadable: boolean;
  created_at?: string | null;
  published_at?: string | null;
  expires_at?: string | null;
  source: { type: string; source_asset_id?: string | null };
}

export interface JobArtifactPage {
  items: JobArtifact[];
  page: { next_cursor?: string | null; has_more: boolean };
  inputs_legacy_unverified?: boolean;
  input_snapshot_failed?: boolean;
}

export interface ArtifactPreview {
  artifact_id: string;
  kind: string;
  mime_type?: string | null;
  truncated: boolean;
  preview_kind: 'text' | 'json' | 'metadata' | string;
  content?: string | null;
  size_bytes?: number | null;
  status: string;
  /** Set when `preview_kind` is `json`: whether `content` parsed as valid JSON. */
  valid_json?: boolean | null;
  /** Set when the preview content was cut short (distinct from `truncated` size cap). */
  partial?: boolean | null;
}

/** Edge in the retry chain graph — present when the chain forks into multiple children. */
export interface JobRetryChainEdge {
  from_job_id: string;
  to_job_id: string;
}

export interface RetryChainAttempt {
  job_id: string;
  attempt_number: number;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  failure_code?: string | null;
  failure_message?: string | null;
  execution_id?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  is_selected: boolean;
  is_current: boolean;
  is_successful: boolean;
}

export interface JobRetryChain {
  root_job_id: string;
  selected_job_id: string;
  current_job_id: string;
  integrity?: string;
  warnings?: string[];
  attempts: RetryChainAttempt[];
  /** Retry graph edges (parent → child); present when the chain forks (integrity FORKED). */
  edges?: JobRetryChainEdge[];
}

export interface ExecutionLogPage {
  inventory_id: string;
  aisle_id: string;
  requested_job_id: string;
  items: ExecutionLogEvent[];
  page: { next_cursor?: string | null; has_more: boolean };
  filters: {
    available_levels: string[];
    available_stages: string[];
    available_event_types: string[];
  };
  pagination_mode?: string;
  truncated?: boolean;
  bytes_scanned?: number | null;
}

export interface JobTimelineEvent {
  id: string;
  job_id: string;
  execution_id?: string | null;
  event_type: string;
  stage?: string | null;
  level: string;
  timestamp?: string | null;
  sequence: number;
  previous_status?: string | null;
  new_status?: string | null;
  message?: string | null;
  duration_ms?: number | null;
  provider?: string | null;
  provider_request_id?: string | null;
  error_code?: string | null;
  metadata?: Record<string, unknown>;
}

export interface JobTimelinePage {
  items: JobTimelineEvent[];
  page: { next_cursor?: string | null; has_more: boolean };
  pagination_mode?: string;
  truncated?: boolean;
  bytes_scanned?: number | null;
}

export interface JobErrorItem {
  error_id: string;
  job_id: string;
  stage?: string | null;
  error_category?: string | null;
  error_code?: string | null;
  provider?: string | null;
  provider_code?: string | null;
  provider_request_id?: string | null;
  http_status?: number | null;
  message?: string | null;
  sanitized_detail?: string | null;
  retryable?: boolean | null;
  attempt_number?: number | null;
  occurred_at?: string | null;
  stack_trace_available: boolean;
}

export interface JobErrorPage {
  items: JobErrorItem[];
  page: { next_cursor?: string | null; has_more: boolean };
  pagination_mode?: string;
  truncated?: boolean;
  bytes_scanned?: number | null;
}

/** Per-job row on GET .../aisles/{aisle_id}/execution-log (aisle aggregate). */
export interface ExecutionLogJobInfo {
  job_id: string;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  prompt_version?: string | null;
  execution_id?: string | null;
}

export interface ExecutionLogSourceInfo {
  job_id: string;
  status: 'ok' | 'missing' | 'error';
  detail?: string | null;
}

/** GET .../aisles/{aisle_id}/execution-log — merged multi-job envelope. */
export interface AisleExecutionLogResponse {
  inventory_id: string;
  aisle_id: string;
  requested_job_id: string | null;
  available_job_ids: string[];
  available_attempts: number[];
  available_execution_ids: string[];
  jobs: ExecutionLogJobInfo[];
  log_sources: ExecutionLogSourceInfo[];
  events: ExecutionLogEvent[];
}

/** Execution log panel accepts single-job or aisle-aggregate envelopes. */
export type ExecutionLogPanelLog = ExecutionLogResponse | AisleExecutionLogResponse;

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
  /** Present when storage metadata captured the size (bytes). */
  file_size_bytes?: number | null;
}

/** Response for POST .../aisles/{aisle_id}/assets (partial success supported). */
export interface AisleAssetUploadErrorItem {
  filename: string;
  code: string;
  detail: string;
  file_index: number;
  client_file_id?: string | null;
}

export interface AisleAssetUploadItem {
  client_file_id?: string | null;
  asset_id: string;
  filename: string;
  status: string;
}

export interface UploadAisleAssetsResponse {
  assets: SourceAssetSummary[];
  batch_id?: string | null;
  uploaded?: AisleAssetUploadItem[];
  errors?: AisleAssetUploadErrorItem[];
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
  /** Phase 4.2: safe to display as operator evidence. */
  has_valid_evidence?: boolean;
  traceability_warning?: string | null;
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
  /** Terminal operator review outcome when set (e.g. confirmed, unknown, image_mismatch). */
  review_resolution?: string | null;
  /** How the position was created: pipeline detection (automatic) or operator manual coverage from an image (manual). Defaults to automatic for legacy rows. */
  creation_source?: 'automatic' | 'manual';
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

/** GET .../jobs/{job_id}/image-results — per-image coverage counters (photos jobs). */
export interface JobImageResultCounters {
  total_images: number;
  with_result: number;
  without_result: number;
}

/** One row of GET .../jobs/{job_id}/image-results: photo LEFT JOIN positions (0..n results per image). */
export interface JobImageResultItem {
  job_source_asset_id: string;
  source_asset_id: string;
  job_id: string;
  image_url: string;
  original_filename?: string | null;
  created_at: string;
  /** 0-based order within the job snapshot; UI displays as #N (1-based). */
  position_order: number;
  processing_status?: string | null;
  has_result: boolean;
  result_count: number;
  automatic_result_count: number;
  manual_result_count: number;
  has_manual_result: boolean;
  results: PositionSummary[];
}

/** GET .../aisles/{aisle_id}/jobs/{job_id}/image-results — paginated by image, not by position. */
export interface JobImageResultsResponse {
  items: JobImageResultItem[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  counters: JobImageResultCounters;
}

/** POST .../assets/{source_asset_id}/manual-result — operator-created coverage for an image without a result. */
export interface CreateManualImageResultResponse {
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
  job_id?: string | null;
}

/** Phase 4.8 — fail-closed structural evidence contract (authoritative for display eligibility). */
export type EvidenceTraceabilityStatusLiteral =
  | 'valid'
  | 'invalid'
  | 'missing'
  | 'unvalidated'
  | 'legacy_unavailable'
  | 'artifact_unavailable';

export type EvidenceSourceKindLiteral =
  | 'structural_result_evidence'
  | 'legacy_json'
  | 'unavailable';

export type ImageAccessStatusLiteral = 'available' | 'url_unavailable' | 'not_allowed';

export interface ResultEvidenceViewResponse {
  displayable: boolean;
  traceability_status: EvidenceTraceabilityStatusLiteral | string;
  traceability_warning?: string | null;
  role?: string | null;
  source_image_id?: string | null;
  source_asset_id?: string | null;
  resolved_manifest_entry_id?: string | null;
  raw_manifest_entry_id?: string | null;
  raw_source_image_id?: string | null;
  image_url?: string | null;
  thumbnail_url?: string | null;
  image_access_status?: ImageAccessStatusLiteral | string | null;
  source_kind: EvidenceSourceKindLiteral | string;
  provider?: string | null;
  model_name?: string | null;
  review_context_displayable?: boolean;
  review_context_image_url?: string | null;
  review_context_warning?: string | null;
}

export interface TraceabilityArtifactMetadataResponse {
  kind: string;
  published: boolean;
  required: boolean;
  status: string;
  storage_key?: string | null;
  content_hash?: string | null;
  size_bytes?: number | null;
  published_at?: string | null;
}

export interface TraceabilitySummaryResponse {
  total_evidence_rows: number;
  valid: number;
  invalid: number;
  missing: number;
  unvalidated: number;
  displayable: number;
  not_displayable: number;
  reference_rejected: number;
  unknown_identifier: number;
  conflicting_identifier: number;
  manifest_unavailable: number;
  manifest_invalid: number;
  artifact_published: number;
}

export interface JobTraceabilityEntityResponse {
  position_id?: string | null;
  entity_uid?: string | null;
  model_entity_id?: string | null;
  evidence: ResultEvidenceViewResponse;
}

/** GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability */
export interface JobTraceabilityResponse {
  job_id: string;
  inventory_id: string;
  aisle_id: string;
  traceability: {
    status?: string;
    artifact?: TraceabilityArtifactMetadataResponse | null;
    summary?: TraceabilitySummaryResponse;
    [key: string]: unknown;
  };
  entities: JobTraceabilityEntityResponse[];
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
  /** Phase 4.8: structural evidence contract (authoritative for display eligibility). */
  evidence?: ResultEvidenceViewResponse | null;
  /** Phase 4.8: durable traceability_manifest metadata for resolved job context. */
  traceability_artifact?: TraceabilityArtifactMetadataResponse | null;
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
