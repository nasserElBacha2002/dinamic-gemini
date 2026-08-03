/**
 * Phase 4 — query read-only product position assignments for a job.
 */

import type { ApiClient } from '../../services/api/apiClient';

export type PositionAssignmentStatus =
  | 'ASSIGNED_AUTOMATIC'
  | 'UNASSIGNED_NO_PREVIOUS_POSITION'
  | 'UNASSIGNED_AFTER_AMBIGUOUS_POSITION'
  | 'UNASSIGNED_INVALID_POSITION'
  | 'UNASSIGNED_UNORDERED_ASSET'
  | 'SKIPPED_NO_ITEM_RESULT';

export interface ProductPositionAssignmentDto {
  readonly id: string;
  readonly result_id: string;
  readonly source_asset_id: string;
  readonly ordered_capture_session_id: string | null;
  readonly sequence_number: number | null;
  readonly position_label_id: string | null;
  readonly position_name: string | null;
  readonly source_detection_id: string | null;
  readonly assignment_status: PositionAssignmentStatus;
  readonly assignment_reason: string;
  readonly assignment_source: string | null;
  readonly reconciliation_id: string;
  readonly reconciliation_version: string;
}

export interface ProductPositionAssignmentListResponse {
  readonly items: readonly ProductPositionAssignmentDto[];
}

export class PositionReconciliationApi {
  constructor(private readonly api: ApiClient) {}

  async listAssignmentsForJob(
    inventoryId: string,
    jobId: string,
  ): Promise<ProductPositionAssignmentListResponse> {
    return this.api.get<ProductPositionAssignmentListResponse>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/jobs/${encodeURIComponent(jobId)}/position-assignments`,
    );
  }
}

export function labelForAssignmentReason(status: PositionAssignmentStatus): string {
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
  }
}

export function formatPositionAssignmentLine(item: ProductPositionAssignmentDto): string {
  if (item.assignment_status === 'ASSIGNED_AUTOMATIC' && item.position_name) {
    return `Producto ${item.result_id}: Posición ${item.position_name}`;
  }
  return (
    `Producto ${item.result_id}: Posición: Sin asignar — ` +
    `Motivo: ${labelForAssignmentReason(item.assignment_status)}`
  );
}
