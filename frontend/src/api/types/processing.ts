/** Phase 7 — operational asset processing observability (v3 API). */

export interface AvailableAssetActions {
  can_reprocess: boolean;
  can_retry_persistence: boolean;
  can_send_to_external: boolean;
  can_assign_manual: boolean;
  can_invalidate: boolean;
  can_view_sensitive_evidence: boolean;
}

export interface AssetProcessingSummary {
  asset_id: string;
  file_name: string | null;
  thumbnail_url: string | null;
  status: string;
  requested_mode: string | null;
  executed_strategy: string | null;
  resolved_by: string | null;
  internal_code: string | null;
  quantity: number | null;
  attempt_count: number;
  last_error_code: string | null;
  warnings: string[];
  duration_ms: number | null;
  persistence_status: string | null;
  has_fallback: boolean;
  has_manual_result: boolean;
  estimated_external_cost: number | null;
  state_version: number;
}

export interface AssetProcessingDetail {
  asset: AssetProcessingSummary;
  current_state: Record<string, unknown>;
  active_result: Record<string, unknown> | null;
  position: Record<string, unknown> | null;
  attempts: Array<Record<string, unknown>>;
  external_requests: Array<Record<string, unknown>>;
  profile_snapshot: Record<string, unknown> | null;
  events: Array<Record<string, unknown>>;
  available_actions: AvailableAssetActions;
  historical_incomplete: boolean;
}

export interface AssetProcessingListResponse {
  items: AssetProcessingSummary[];
  total: number;
  page: number;
  page_size: number;
  summary?: ProcessingJobProgressSummary | null;
}

export interface ProcessingJobProgressSummary {
  total: number;
  resolved: number;
  failed: number;
  pending: number;
  processing: number;
  manual_review: number;
  unrecognized?: number;
  cancelled?: number;
}

export interface ProcessingEventRecord {
  id: string;
  event_type: string;
  timestamp: string;
  level?: string | null;
  message?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ProcessingEventsPage {
  items: ProcessingEventRecord[];
  total: number;
  page: number;
  page_size: number;
  has_more?: boolean;
}

export interface ProcessingObservabilityCapabilities {
  processing_observability_enabled: boolean;
  processing_asset_logs_ui_enabled?: boolean;
  processing_asset_reprocess_enabled?: boolean;
  processing_manual_actions_enabled?: boolean;
  processing_events_persistence_enabled?: boolean;
}

export interface ReprocessAssetRequest {
  strategy?: string;
  reason: string;
  expected_state_version: number;
  manual_policy?: string;
}

export interface InvalidateResultRequest {
  reason: string;
  expected_state_version: number;
}

export interface ReprocessAssetResponse {
  asset_id: string;
  state_version: number;
  status?: string;
}

export interface InvalidateResultResponse {
  asset_id: string;
  state_version: number;
  status?: string;
}
