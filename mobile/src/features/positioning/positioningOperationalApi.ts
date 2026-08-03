/**
 * Phase 7 — minimal mobile operational positioning client (allowed_actions from backend).
 */

import type { ApiClient } from '../../services/api/apiClient';

export interface PositioningAllowedActionsDto {
  readonly process: boolean;
  readonly reprocess: boolean;
  readonly recover: boolean;
  readonly review: boolean;
  readonly correct_position: boolean;
  readonly restore_automatic: boolean;
  readonly reconcile_only: boolean;
}

export interface PositioningWarningDto {
  readonly code: string;
  readonly title: string;
  readonly description: string;
  readonly severity: string;
  readonly affected_count: number;
  readonly allowed_actions: readonly string[];
}

export interface AisleOperationalPositioningViewDto {
  readonly processing_state: string;
  readonly active_job_id: string | null;
  readonly result_job_id: string | null;
  readonly reconciliation_status: string | null;
  readonly reconciliation_version: string | null;
  readonly total_results: number;
  readonly assigned_results: number;
  readonly unassigned_results: number;
  readonly manual_overrides_count: number;
  readonly detections_count: number;
  readonly recoverable: boolean;
  readonly allowed_actions: PositioningAllowedActionsDto;
  readonly warnings: readonly PositioningWarningDto[];
  readonly supported_reprocess_modes: readonly string[];
  readonly feature_flags: Readonly<Record<string, boolean>>;
}

export interface PositioningSequenceDto {
  readonly job_id: string;
  readonly items: readonly {
    readonly sequence_number: number | null;
    readonly source_asset_id: string;
    readonly filename: string | null;
    readonly position_label_name: string | null;
    readonly effective_assignment_summaries: readonly string[];
  }[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
}

export interface PositioningReprocessResponseDto {
  readonly mode: string;
  readonly job_id: string | null;
  readonly reconciliation_id: string | null;
  readonly detail: string;
  readonly manuals_preserved: boolean;
  readonly manual_override_policy: string;
  readonly previous_manual_overrides_count: number;
}

function aisleBase(inventoryId: string, aisleId: string): string {
  return `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}`;
}

export class PositioningOperationalApi {
  constructor(private readonly api: ApiClient) {}

  getOperationalView(
    inventoryId: string,
    aisleId: string,
  ): Promise<AisleOperationalPositioningViewDto> {
    return this.api.get<AisleOperationalPositioningViewDto>(
      `${aisleBase(inventoryId, aisleId)}/positioning-operational-view`,
    );
  }

  getSequence(
    inventoryId: string,
    aisleId: string,
    jobId: string,
    page = 1,
    pageSize = 20,
  ): Promise<PositioningSequenceDto> {
    const q = new URLSearchParams({
      job_id: jobId,
      page: String(page),
      page_size: String(pageSize),
    });
    return this.api.get<PositioningSequenceDto>(
      `${aisleBase(inventoryId, aisleId)}/positioning-sequence?${q}`,
    );
  }

  reprocess(
    inventoryId: string,
    aisleId: string,
    body: {
      readonly idempotency_key: string;
      readonly reprocess_mode: string;
      readonly expected_active_job_id?: string | null;
      readonly expected_result_job_id?: string | null;
    },
  ): Promise<PositioningReprocessResponseDto> {
    return this.api.post<PositioningReprocessResponseDto>(
      `${aisleBase(inventoryId, aisleId)}/reprocess`,
      {
        idempotency_key: body.idempotency_key,
        reprocess_mode: body.reprocess_mode,
        expected_active_job_id: body.expected_active_job_id ?? null,
        expected_result_job_id: body.expected_result_job_id ?? null,
        identification_mode: null,
      },
    );
  }
}
