import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export type PositionOverrideAction =
  | 'ASSIGN_POSITION'
  | 'CHANGE_POSITION'
  | 'REMOVE_POSITION';

export type PositionOverrideReasonCode =
  | 'WRONG_POSITION_DETECTED'
  | 'PRODUCT_MOVED'
  | 'SEQUENCE_ERROR'
  | 'POSITION_LABEL_NOT_VISIBLE'
  | 'POSITION_LABEL_INVALID'
  | 'AMBIGUOUS_IMAGE'
  | 'MISSING_POSITION_LABEL'
  | 'OPERATOR_VERIFICATION'
  | 'DATA_CORRECTION'
  | 'OTHER';

export interface PositionOverrideRequest {
  action: PositionOverrideAction;
  position_label_id?: string | null;
  reason_code: PositionOverrideReasonCode;
  reason_text?: string | null;
  expected_version: number;
  idempotency_key: string;
}

export interface RestoreAutomaticRequest {
  reason_code: PositionOverrideReasonCode;
  reason_text?: string | null;
  expected_version: number;
  idempotency_key: string;
}

export interface PositionOverrideRevision {
  id: string;
  action: string;
  reason_code: string;
  reason_text: string | null;
  position_label_id: string | null;
  position_name: string | null;
  created_by_user_id: string;
  created_by_role: string;
  created_at: string;
  deactivated_at: string | null;
  version: number;
  is_active: boolean;
}

export interface EffectivePosition {
  result_id: string;
  position: { id: string | null; name: string | null } | null;
  source: 'AUTOMATIC' | 'MANUAL' | 'NONE' | string;
  status: string;
  automatic_position: { id: string | null; name: string | null } | null;
  automatic_assignment_status: string | null;
  reconciliation_status: string | null;
  manual_override: PositionOverrideRevision | null;
  warnings: string[];
  version: number;
}

export interface PositionOverrideMutationResponse {
  revision: PositionOverrideRevision;
  /** Effective position after the mutation or on idempotent replay (always current). */
  current_effective: EffectivePosition;
}

export interface PositionHistoryResponse {
  effective: EffectivePosition;
  automatic_revisions: Array<{
    id: string;
    reconciliation_id: string;
    position_label_id: string | null;
    position_name: string | null;
    assignment_status: string;
    assignment_reason: string;
    is_active: boolean;
    created_at: string;
    superseded_at: string | null;
  }>;
  manual_revisions: PositionOverrideRevision[];
}

function overrideBase(
  inventoryId: string,
  jobId: string,
  resultId: string
): string {
  return (
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
    `/jobs/${encodeURIComponent(jobId)}/results/${encodeURIComponent(resultId)}`
  );
}

export function createOverride(
  inventoryId: string,
  jobId: string,
  resultId: string,
  body: PositionOverrideRequest
): Promise<PositionOverrideMutationResponse> {
  return apiRequestJson(`${overrideBase(inventoryId, jobId, resultId)}/position-override`, {
    method: 'POST',
    body,
  });
}

export function restoreAutomatic(
  inventoryId: string,
  jobId: string,
  resultId: string,
  body: RestoreAutomaticRequest
): Promise<PositionOverrideMutationResponse> {
  return apiRequestJson(
    `${overrideBase(inventoryId, jobId, resultId)}/position-override/restore`,
    { method: 'POST', body }
  );
}

export function getHistory(
  inventoryId: string,
  jobId: string,
  resultId: string
): Promise<PositionHistoryResponse> {
  return apiRequestJson(`${overrideBase(inventoryId, jobId, resultId)}/position-history`);
}
