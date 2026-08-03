/**
 * Phase 4 — read-only product position assignments and reconciliation diagnostics.
 */

import { apiRequestJson } from './request';

export type PositionAssignmentStatus =
  | 'ASSIGNED_AUTOMATIC'
  | 'UNASSIGNED_NO_PREVIOUS_POSITION'
  | 'UNASSIGNED_AFTER_AMBIGUOUS_POSITION'
  | 'UNASSIGNED_INVALID_POSITION'
  | 'UNASSIGNED_UNORDERED_ASSET'
  | 'SKIPPED_NO_ITEM_RESULT';

export interface ProductPositionAssignmentDto {
  id: string;
  result_id: string;
  source_asset_id: string;
  ordered_capture_session_id: string | null;
  sequence_number: number | null;
  position_label_id: string | null;
  position_name: string | null;
  source_detection_id: string | null;
  assignment_status: PositionAssignmentStatus;
  assignment_reason: string;
  assignment_source: string | null;
  reconciliation_id: string;
  reconciliation_version: string;
}

export interface ProductPositionAssignmentListResponse {
  items: ProductPositionAssignmentDto[];
}

export interface PositionReconciliationDto {
  id: string;
  job_id: string;
  ordered_capture_session_id: string | null;
  reconciliation_name: string;
  reconciliation_version: string;
  input_fingerprint: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  failure_code: string | null;
  attempt_count: number;
  assigned_count: number;
  unassigned_count: number;
  sequence_gap_count: number;
  metadata: Record<string, unknown>;
}

function jobPath(inventoryId: string, jobId: string): string {
  return `/api/v3/inventories/${encodeURIComponent(inventoryId)}/jobs/${encodeURIComponent(jobId)}`;
}

export async function getJobPositionReconciliation(
  inventoryId: string,
  jobId: string,
): Promise<PositionReconciliationDto> {
  return apiRequestJson<PositionReconciliationDto>(
    `${jobPath(inventoryId, jobId)}/position-reconciliation`,
  );
}

export async function listJobPositionAssignments(
  inventoryId: string,
  jobId: string,
): Promise<ProductPositionAssignmentListResponse> {
  return apiRequestJson<ProductPositionAssignmentListResponse>(
    `${jobPath(inventoryId, jobId)}/position-assignments`,
  );
}

export async function listJobUnassignedResults(
  inventoryId: string,
  jobId: string,
): Promise<ProductPositionAssignmentListResponse> {
  return apiRequestJson<ProductPositionAssignmentListResponse>(
    `${jobPath(inventoryId, jobId)}/unassigned-results`,
  );
}

export async function retryJobPositionReconciliation(
  inventoryId: string,
  jobId: string,
): Promise<PositionReconciliationDto> {
  return apiRequestJson<PositionReconciliationDto>(
    `${jobPath(inventoryId, jobId)}/position-reconciliation/retry`,
    { method: 'POST' },
  );
}

export function labelForPositionAssignmentStatus(status: string): string {
  switch (status) {
    case 'ASSIGNED_AUTOMATIC':
      return 'Automática';
    case 'UNASSIGNED_NO_PREVIOUS_POSITION':
      return 'Sin posición previa';
    case 'UNASSIGNED_AFTER_AMBIGUOUS_POSITION':
      return 'Después de posición ambigua';
    case 'UNASSIGNED_INVALID_POSITION':
      return 'Posición inválida';
    case 'UNASSIGNED_UNORDERED_ASSET':
      return 'Imagen sin secuencia';
    case 'SKIPPED_NO_ITEM_RESULT':
      return 'Sin resultado de producto';
    default:
      return status;
  }
}
