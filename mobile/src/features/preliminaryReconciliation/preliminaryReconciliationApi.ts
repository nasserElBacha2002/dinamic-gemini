import type { ApiClient } from '../../services/api/apiClient';

export interface ReconcilePreliminaryRequest {
  readonly job_id: string;
  readonly enqueue_limit?: number;
}

export interface ReconcilePreliminaryResponse {
  readonly accepted: boolean;
  readonly batch_id: string;
  readonly enqueued: number;
  readonly already_terminal: number;
  readonly reconciliation_ids: readonly string[];
  readonly status: string;
}

export interface PreliminaryReconciliationItem {
  readonly id: string;
  readonly preliminary_detection_id: string;
  readonly asset_id: string;
  readonly client_file_id: string;
  readonly job_id: string;
  readonly outcome: string;
  readonly not_comparable_reason: string | null;
  readonly local_status: string;
  readonly remote_status: string | null;
  readonly local_parser_version: string | null;
  readonly local_detector_version: string | null;
  readonly compared_at: string;
  readonly reconciliation_status: string;
  readonly comparison_version: string;
}

export interface ReconciliationMetrics {
  readonly total_eligible_drafts?: number;
  readonly total_reconciled?: number;
  readonly total_local_drafts?: number;
  readonly total_comparable?: number;
  readonly mapping_comparable?: number;
  readonly total_not_comparable: number;
  readonly code_match_count?: number;
  readonly code_mismatch_count?: number;
  readonly server_agreement_rate?: number | null;
  readonly server_code_agreement_rate?: number | null;
  readonly comparability_rate?: number | null;
}

export interface ListPreliminaryReconciliationsResponse {
  readonly items: readonly PreliminaryReconciliationItem[];
  readonly total: number;
  readonly metrics: ReconciliationMetrics;
  readonly authority_notice: string;
}

export class PreliminaryReconciliationApi {
  constructor(private readonly api: ApiClient) {}

  async triggerReconcile(
    inventoryId: string,
    aisleId: string,
    body: ReconcilePreliminaryRequest,
  ): Promise<ReconcilePreliminaryResponse> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/reconcile-preliminary-detections`;
    return this.api.post<ReconcilePreliminaryResponse>(path, body, { timeoutMs: 60_000 });
  }

  async listForAisle(
    inventoryId: string,
    aisleId: string,
    params?: {
      readonly jobId?: string;
      readonly preliminaryDetectionId?: string;
      readonly comparisonVersion?: string;
      readonly limit?: number;
    },
  ): Promise<ListPreliminaryReconciliationsResponse> {
    const q = new URLSearchParams();
    if (params?.jobId) {
      q.set('job_id', params.jobId);
    }
    if (params?.preliminaryDetectionId) {
      q.set('preliminary_detection_id', params.preliminaryDetectionId);
    }
    if (params?.comparisonVersion) {
      q.set('comparison_version', params.comparisonVersion);
    }
    if (params?.limit != null) {
      q.set('limit', String(params.limit));
    }
    const qs = q.toString();
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/preliminary-reconciliations` +
      (qs ? `?${qs}` : '');
    return this.api.get<ListPreliminaryReconciliationsResponse>(path, { timeoutMs: 30_000 });
  }
}
