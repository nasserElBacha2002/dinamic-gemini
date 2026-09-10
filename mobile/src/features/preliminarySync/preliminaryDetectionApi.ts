import type { ApiClient } from '../../services/api/apiClient';
import { normalizeLocalPositionCode } from '../../core/positionLabelPayload';

export interface PreliminaryDetectionSyncRequest {
  readonly schema_version: '1' | '2';
  readonly capture_session_id: string;
  readonly capture_photo_id: string;
  readonly client_file_id: string;
  readonly asset_id: string;
  readonly processing_mode: 'CODE_SCAN';
  readonly status: string;
  readonly internal_code: string | null;
  readonly quantity: number | null;
  readonly quantity_status: string | null;
  readonly detected_format: string | null;
  readonly detected_symbology: string | null;
  readonly candidate_count: number;
  readonly parser_version: string;
  readonly detector_version: string;
  readonly prepared_asset_sha256: string;
  readonly payload_hash: string | null;
  readonly processing_ms: number | null;
  readonly detected_at: string | null;
  readonly position_reference?: PositionSyncReferenceV2;
}

export interface PositionSyncReferenceV2 {
  readonly payload_version: 2;
  readonly local_recognition_id: string;
  readonly raw_code: string;
  readonly normalized_code: string;
  readonly remote_position_id: string | null;
  readonly remote_position_label_id: string | null;
  readonly source: string;
  readonly profile_id: string | null;
  readonly profile_version: number | null;
  readonly client_supplier_id: string | null;
  readonly signature: {
    readonly present: boolean;
    readonly verification: 'MISSING' | 'UNVERIFIED' | 'INVALID' | 'NOT_APPLICABLE';
  };
  readonly captured_at: string;
}

export type PositionAuthoritativeStatus =
  | 'ACCEPTED_EXISTING'
  | 'ACCEPTED_UNMATERIALIZED'
  | 'MATERIALIZED'
  | 'REUSED'
  | 'REJECTED_FORMAT'
  | 'REJECTED_VALIDATION'
  | 'REJECTED_PROFILE'
  | 'REJECTED_SCOPE'
  | 'REJECTED_INVENTORY_STATE'
  | 'REJECTED_AMBIGUOUS'
  | 'REJECTED_CONFLICT'
  | 'REJECTED_DUPLICATE'
  | 'RETRYABLE_ERROR'
  | 'INVARIANT_VIOLATION';

export interface PositionSyncResultV2 {
  readonly contract_version: 2;
  readonly local_recognition_id: string;
  readonly normalized_code: string | null;
  readonly remote_position_id: string | null;
  readonly remote_position_label_id: string | null;
  readonly status: PositionAuthoritativeStatus;
  readonly error_code: string | null;
  readonly retryable: boolean;
  readonly server_timestamp: string;
  readonly reconciliation_revision: number;
  readonly created: boolean;
  readonly idempotent_replay: boolean;
}

const POSITION_STATUSES = new Set<PositionAuthoritativeStatus>([
  'ACCEPTED_EXISTING',
  'ACCEPTED_UNMATERIALIZED',
  'MATERIALIZED',
  'REUSED',
  'REJECTED_FORMAT',
  'REJECTED_VALIDATION',
  'REJECTED_PROFILE',
  'REJECTED_SCOPE',
  'REJECTED_INVENTORY_STATE',
  'REJECTED_AMBIGUOUS',
  'REJECTED_CONFLICT',
  'REJECTED_DUPLICATE',
  'RETRYABLE_ERROR',
  'INVARIANT_VIOLATION',
]);

export function parsePositionSyncResultV2(value: unknown): PositionSyncResultV2 | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (
    row.contract_version !== 2 ||
    typeof row.local_recognition_id !== 'string' ||
    !row.local_recognition_id.trim() ||
    typeof row.status !== 'string' ||
    !POSITION_STATUSES.has(row.status as PositionAuthoritativeStatus) ||
    typeof row.retryable !== 'boolean' ||
    typeof row.server_timestamp !== 'string' ||
    !Number.isFinite(Date.parse(row.server_timestamp)) ||
    typeof row.reconciliation_revision !== 'number' ||
    !Number.isInteger(row.reconciliation_revision) ||
    row.reconciliation_revision < 0
  ) {
    return null;
  }
  if (
    (row.created !== undefined && typeof row.created !== 'boolean') ||
    (row.idempotent_replay !== undefined &&
      typeof row.idempotent_replay !== 'boolean')
  ) {
    return null;
  }
  const optionalText = (candidate: unknown): string | null | undefined => {
    if (candidate === null) return null;
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
    return undefined;
  };
  const normalizedCode = optionalText(row.normalized_code);
  const remotePositionId = optionalText(row.remote_position_id);
  const remotePositionLabelId = optionalText(row.remote_position_label_id);
  const errorCode = optionalText(row.error_code);
  if (
    normalizedCode === undefined ||
    remotePositionId === undefined ||
    remotePositionLabelId === undefined ||
    errorCode === undefined
  ) {
    return null;
  }
  let canonicalCode: string | null = null;
  if (normalizedCode !== null) {
    try {
      canonicalCode = normalizeLocalPositionCode(normalizedCode);
    } catch {
      return null;
    }
  }
  const status = row.status as PositionAuthoritativeStatus;
  const created = row.created === true;
  const idempotentReplay = row.idempotent_replay === true;
  if (
    row.retryable !== (status === 'RETRYABLE_ERROR') ||
    (created && (status !== 'MATERIALIZED' || idempotentReplay)) ||
    ((status === 'MATERIALIZED' || status === 'REUSED') &&
      remotePositionId === null)
  ) {
    return null;
  }
  return {
    contract_version: 2,
    local_recognition_id: row.local_recognition_id.trim(),
    normalized_code: canonicalCode,
    remote_position_id: remotePositionId,
    remote_position_label_id: remotePositionLabelId,
    status,
    error_code: errorCode,
    retryable: row.retryable,
    server_timestamp: row.server_timestamp,
    reconciliation_revision: row.reconciliation_revision,
    created,
    idempotent_replay: idempotentReplay,
  };
}

export interface PreliminaryDetectionSyncResponse {
  readonly draft_id: string;
  readonly server_preliminary_id: string;
  readonly status: string;
  readonly received_at: string;
  readonly validation_errors: readonly string[];
  readonly duplicate?: boolean;
  readonly position_result?: PositionSyncResultV2 | null;
}

export class PreliminaryDetectionApi {
  constructor(private readonly api: ApiClient) {}

  async upsertDraft(
    inventoryId: string,
    aisleId: string,
    draftId: string,
    body: PreliminaryDetectionSyncRequest,
  ): Promise<PreliminaryDetectionSyncResponse> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}` +
      `/preliminary-detections/${encodeURIComponent(draftId)}`;
    return this.api.put<PreliminaryDetectionSyncResponse>(path, body, {
      timeoutMs: 30_000,
    });
  }
}
