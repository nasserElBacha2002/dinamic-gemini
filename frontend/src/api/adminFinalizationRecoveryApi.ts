import { V3_API_PREFIX } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export type FinalizationRecoveryOperation =
  | 'verify'
  | 'republish_artifacts'
  | 'terminalize'
  | 'promote'
  | 'reconcile_aisle'
  | 'reconcile_inventory'
  | 'resume';

export interface AdminFinalizationRecoveryRequest {
  operation: FinalizationRecoveryOperation;
  dry_run: boolean;
  allow_canceled_terminalization?: boolean;
  include_optional_artifacts?: boolean;
}

export interface AdminFinalizationRecoveryResponse {
  job_id: string;
  operation: string;
  outcome: string;
  dry_run: boolean;
  recovery_id?: string | null;
  error_code?: string | null;
  sanitized_message?: string | null;
  previous_assessment_outcome: string;
  new_assessment_outcome: string;
  eligible_operations: string[];
  blocked_operations: string[];
  stages_attempted: string[];
  stages_completed: string[];
  stages_skipped: string[];
}

export function getAdminFinalizationRecoverPath(jobId: string): string {
  return `${V3_API_PREFIX}/admin/jobs/${encodeURIComponent(jobId)}/finalization/recover`;
}

export async function postAdminFinalizationRecover(
  jobId: string,
  body: AdminFinalizationRecoveryRequest
): Promise<AdminFinalizationRecoveryResponse> {
  return apiRequestJson<AdminFinalizationRecoveryResponse>(
    `${API_BASE}${getAdminFinalizationRecoverPath(jobId)}`,
    { method: 'POST', body }
  );
}
