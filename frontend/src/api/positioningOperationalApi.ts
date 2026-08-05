import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface PositioningAllowedActionsDto {
  process: boolean;
  reprocess: boolean;
  recover: boolean;
  review: boolean;
  correct_position: boolean;
  restore_automatic: boolean;
  reconcile_only: boolean;
}

export interface PositioningWarningDto {
  code: string;
  title: string;
  description: string;
  severity: string;
  affected_count: number;
  allowed_actions: string[];
}

export interface UnassignedCauseBucketDto {
  cause: string;
  count: number;
  suggested_action: string;
}

export interface AisleOperationalPositioningViewDto {
  inventory_id: string;
  aisle_id: string;
  client_id: string | null;
  processing_state: string;
  active_job_id: string | null;
  result_job_id: string | null;
  reconciliation_status: string | null;
  reconciliation_id: string | null;
  reconciliation_version: string | null;
  total_results: number;
  assigned_results: number;
  unassigned_results: number;
  assigned_automatic: number;
  assigned_manual: number;
  unassigned_automatic: number;
  unassigned_manual: number;
  manual_overrides_count: number;
  invalid_positions_count: number;
  stale_results_count: number;
  unordered_assets_count: number;
  ambiguous_detections_count: number;
  detections_count: number;
  recoverable: boolean;
  can_process: boolean;
  can_reprocess: boolean;
  can_recover: boolean;
  can_review: boolean;
  can_correct: boolean;
  allowed_actions: PositioningAllowedActionsDto;
  warnings: PositioningWarningDto[];
  unassigned_by_cause: UnassignedCauseBucketDto[];
  supported_reprocess_modes: string[];
  last_updated_at: string | null;
  feature_flags: Record<string, boolean>;
}

export interface PositioningSequenceFrameDto {
  sequence_number: number | null;
  source_asset_id: string;
  filename: string | null;
  position_detection_status: string | null;
  position_label_name: string | null;
  transition_action: string | null;
  transition_message: string | null;
  product_count: number;
  automatic_assignment_summaries: string[];
  effective_assignment_summaries: string[];
  warnings: string[];
  reason_code?: string | null;
  position_label_id?: string | null;
}

export interface PositioningSequenceDto {
  job_id: string;
  items: PositioningSequenceFrameDto[];
  total: number;
  page: number;
  page_size: number;
}

export interface PositioningReprocessRequest {
  idempotency_key: string;
  reprocess_mode: 'REPROCESS_FULL_AISLE' | 'RECONCILE_ONLY' | string;
  expected_active_job_id?: string | null;
  expected_result_job_id?: string | null;
  identification_mode?: string | null;
}

export interface PositioningReprocessResponse {
  mode: string;
  job_id: string | null;
  reconciliation_id: string | null;
  detail: string;
  manuals_preserved: boolean;
  manual_override_policy: string;
  previous_manual_overrides_count: number;
}

export async function getAislePositioningOperationalView(
  inventoryId: string,
  aisleId: string,
  jobId?: string | null,
): Promise<AisleOperationalPositioningViewDto> {
  const q = jobId ? `?job_id=${encodeURIComponent(jobId)}` : '';
  return apiRequestJson<AisleOperationalPositioningViewDto>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positioning-operational-view${q}`,
  );
}

export async function getAislePositioningSequence(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  page = 1,
  pageSize = 50,
): Promise<PositioningSequenceDto> {
  const q = new URLSearchParams({
    job_id: jobId,
    page: String(page),
    page_size: String(pageSize),
  });
  return apiRequestJson<PositioningSequenceDto>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positioning-sequence?${q}`,
  );
}

export async function reprocessAislePositioning(
  inventoryId: string,
  aisleId: string,
  body: PositioningReprocessRequest,
): Promise<PositioningReprocessResponse> {
  return apiRequestJson<PositioningReprocessResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/reprocess`,
    {
      method: 'POST',
      body: {
        idempotency_key: body.idempotency_key,
        reprocess_mode: body.reprocess_mode,
        expected_active_job_id: body.expected_active_job_id ?? null,
        expected_result_job_id: body.expected_result_job_id ?? null,
        identification_mode: body.identification_mode ?? null,
      },
    },
  );
}
