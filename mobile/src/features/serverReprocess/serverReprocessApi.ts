import type { ApiClient } from '../../services/api/apiClient';

export type ServerReprocessScopeType =
  | 'FULL_AISLE'
  | 'SELECTED_ASSETS'
  | 'FAILED_ONLY'
  | 'UNRECOGNIZED_ONLY'
  | 'PENDING_REVIEW_ONLY';

export type ServerReprocessProcessingMode =
  | 'CODE_SCAN'
  | 'INTERNAL_OCR'
  | 'GLOBAL_FALLBACK'
  | 'AUTO_PIPELINE';

export interface ServerReprocessRunDto {
  readonly id: string;
  readonly request_id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly run_type: string;
  readonly scope_type: string;
  readonly processing_mode: string;
  readonly status: string;
  readonly review_status: string;
  readonly has_prior_authority: boolean;
  readonly initial_server_processing?: boolean;
  readonly has_pending_server_reprocess?: boolean;
}

export interface ServerReprocessProposalItemDto {
  readonly id: string;
  readonly asset_id: string;
  readonly status: string;
  readonly difference_type: string;
  readonly internal_code: string | null;
  readonly quantity: number | null;
  readonly previous_result_id: string | null;
  readonly remote_resolved: boolean;
  readonly review_status: string;
}

export interface ServerReprocessDetailDto {
  readonly run: ServerReprocessRunDto;
  readonly summary: {
    readonly total: number;
    readonly same: number;
    readonly changed: number;
    readonly newly_resolved: number;
    readonly unresolved: number;
  };
  readonly items: readonly ServerReprocessProposalItemDto[];
}

export interface ServerReprocessAdoptItem {
  readonly proposal_id: string;
  readonly action: 'ADOPT' | 'KEEP_CURRENT' | 'EDIT_AND_ADOPT' | 'DEFER';
  readonly edit_internal_code?: string | null;
  readonly edit_quantity?: number | null;
}

export class ServerReprocessApi {
  constructor(private readonly api: ApiClient) {}

  async requestReprocess(
    inventoryId: string,
    aisleId: string,
    body: {
      request_id: string;
      scope: { type: ServerReprocessScopeType; asset_ids?: string[] };
      processing_mode: ServerReprocessProcessingMode;
      reason?: string;
    },
  ): Promise<ServerReprocessRunDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/server-reprocess`;
    return this.api.post<ServerReprocessRunDto>(path, body, { timeoutMs: 30_000 });
  }

  async getRun(
    inventoryId: string,
    aisleId: string,
    runId: string,
  ): Promise<ServerReprocessDetailDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/server-reprocess/${encodeURIComponent(runId)}`;
    return this.api.get<ServerReprocessDetailDto>(path, { timeoutMs: 15_000 });
  }

  async adopt(
    inventoryId: string,
    aisleId: string,
    runId: string,
    body: { adoption_id: string; items: ServerReprocessAdoptItem[] },
  ): Promise<{ adoption_id: string; review_status: string; replayed: boolean }> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}` +
      `/server-reprocess/${encodeURIComponent(runId)}/adopt`;
    return this.api.post(path, body, { timeoutMs: 60_000 });
  }

  async cancel(inventoryId: string, aisleId: string, runId: string): Promise<ServerReprocessRunDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}` +
      `/server-reprocess/${encodeURIComponent(runId)}/cancel`;
    return this.api.post<ServerReprocessRunDto>(path, {}, { timeoutMs: 15_000 });
  }
}
