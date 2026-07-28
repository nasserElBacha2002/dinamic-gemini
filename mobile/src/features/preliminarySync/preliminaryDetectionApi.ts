import type { ApiClient } from '../../services/api/apiClient';

export interface PreliminaryDetectionSyncRequest {
  readonly schema_version: string;
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
}

export interface PreliminaryDetectionSyncResponse {
  readonly draft_id: string;
  readonly server_preliminary_id: string;
  readonly status: string;
  readonly received_at: string;
  readonly validation_errors: readonly string[];
  readonly duplicate?: boolean;
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
