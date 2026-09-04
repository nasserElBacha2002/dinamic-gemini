import type { ApiClient } from '../../services/api/apiClient';

export interface AuthoritativeLocalCodeScanRequest {
  readonly schema_version: string;
  readonly result_id: string;
  readonly client_file_id: string;
  /** Required for Dinamic; null for SUPPLIER identity-only (label_id present). */
  readonly internal_code: string | null;
  readonly quantity: number | null;
  readonly quantity_status: 'PRESENT' | 'MISSING';
  readonly source: 'LOCAL_CODE_SCAN' | 'LOCAL_MANUAL_CORRECTION';
  /** Optional D1 physical sticker id (additive; omit/null for legacy). */
  readonly label_id?: string | null;
  readonly detected_internal_code: string | null;
  readonly detected_quantity: number | null;
  readonly detected_symbology: string | null;
  readonly parser_version: string;
  readonly detector_version: string;
  readonly prepared_asset_sha256: string;
  readonly confirmed_at: string;
  readonly profile_source?: 'DINAMIC' | 'SUPPLIER' | null;
  readonly profile_id?: string | null;
  readonly profile_version?: number | null;
  readonly configuration_schema_version?: number | null;
  readonly label_kind?: 'ITEM' | 'POSITION' | null;
  readonly client_supplier_id?: string | null;
  readonly raw_payload?: string | null;
  readonly recognition_status?: string | null;
  readonly captured_offline?: boolean | null;
  readonly captured_with_older_profile?: boolean | null;
}

export interface AuthoritativeLocalCodeScanResponse {
  readonly result_id: string;
  readonly asset_id: string;
  readonly result_version: number;
  readonly is_current: boolean;
  readonly supersedes_result_id: string | null;
  readonly status: string;
  readonly duplicate?: boolean;
  /** Present only after final position apply; null while AUTHORITATIVE_SYNCED only. */
  readonly applied_at?: string | null;
}

export class AuthoritativeLocalResultApi {
  constructor(private readonly api: ApiClient) {}

  async upsertResult(
    inventoryId: string,
    aisleId: string,
    assetId: string,
    body: AuthoritativeLocalCodeScanRequest,
  ): Promise<AuthoritativeLocalCodeScanResponse> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}` +
      `/assets/${encodeURIComponent(assetId)}` +
      `/authoritative-code-scan`;
    return this.api.put<AuthoritativeLocalCodeScanResponse>(path, body, {
      timeoutMs: 30_000,
    });
  }
}
