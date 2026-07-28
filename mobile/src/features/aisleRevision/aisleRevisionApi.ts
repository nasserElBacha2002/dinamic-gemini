import type { ApiClient } from '../../services/api/apiClient';

export type AisleRevisionType =
  | 'MANUAL_CORRECTION'
  | 'SERVER_PROPOSAL_ADOPTION'
  | 'ROLLBACK'
  | 'EXCLUSION_CHANGE'
  | 'REOPEN_AND_EDIT';

export interface AisleRevisionDto {
  readonly id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly base_finalization_id: string;
  readonly new_finalization_id: string | null;
  readonly revision_type: string;
  readonly status: string;
  readonly reason: string;
  readonly requested_by: string;
  readonly requested_at: string;
  readonly completed_at: string | null;
}

export interface AisleRevisionItemDto {
  readonly id: string;
  readonly asset_id: string;
  readonly proposed_internal_code: string | null;
  readonly proposed_quantity: number | null;
  readonly item_status: string;
  readonly proposal_source: string;
}

export interface AisleRevisionDiffEntryDto {
  readonly asset_id: string;
  readonly kind: string;
  readonly base_internal_code: string | null;
  readonly proposed_internal_code: string | null;
  readonly base_quantity: number | null;
  readonly proposed_quantity: number | null;
  readonly item_status: string;
  readonly proposal_source: string;
}

export interface AisleRevisionDiffDto {
  readonly revision: AisleRevisionDto;
  readonly entries: readonly AisleRevisionDiffEntryDto[];
}

export interface AisleRevisionHistoryEntryDto {
  readonly revision_id: string;
  readonly revision_type: string;
  readonly status: string;
  readonly reason: string;
  readonly requested_by: string;
  readonly requested_at: string;
  readonly completed_at: string | null;
  readonly base_finalization_id: string;
  readonly new_finalization_id: string | null;
  readonly changed_asset_count: number;
  readonly total_assets: number;
}

export class AisleRevisionApi {
  constructor(private readonly api: ApiClient) {}

  async createRevision(
    inventoryId: string,
    aisleId: string,
    body: {
      revision_id: string;
      revision_type: AisleRevisionType;
      reason: string;
      requested_by: string;
      target_finalization_id?: string | null;
    },
  ): Promise<AisleRevisionDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/revisions`;
    return this.api.post<AisleRevisionDto>(path, body, { timeoutMs: 30_000 });
  }

  async updateItem(
    inventoryId: string,
    aisleId: string,
    revisionId: string,
    assetId: string,
    body: {
      internal_code?: string | null;
      quantity?: number | null;
      exclusion_action?: 'EXCLUDE' | 'RESTORE' | null;
      reason?: string | null;
      proposal_source?: string | null;
      proposal_reference_id?: string | null;
    },
  ): Promise<AisleRevisionItemDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/revisions/${encodeURIComponent(revisionId)}` +
      `/items/${encodeURIComponent(assetId)}`;
    return this.api.put<AisleRevisionItemDto>(path, body, { timeoutMs: 15_000 });
  }

  async apply(
    inventoryId: string,
    aisleId: string,
    revisionId: string,
    body: {
      apply_id: string;
      expected_base_finalization_id: string;
      applied_by: string;
    },
  ): Promise<AisleRevisionDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/revisions/${encodeURIComponent(revisionId)}/apply`;
    return this.api.post<AisleRevisionDto>(path, body, { timeoutMs: 60_000 });
  }

  async getDiff(
    inventoryId: string,
    aisleId: string,
    revisionId: string,
  ): Promise<AisleRevisionDiffDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/revisions/${encodeURIComponent(revisionId)}/diff`;
    return this.api.get<AisleRevisionDiffDto>(path, { timeoutMs: 15_000 });
  }

  async getHistory(
    inventoryId: string,
    aisleId: string,
  ): Promise<readonly AisleRevisionHistoryEntryDto[]> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/revision-history`;
    return this.api.get<readonly AisleRevisionHistoryEntryDto[]>(path, { timeoutMs: 15_000 });
  }

  async rollback(
    inventoryId: string,
    aisleId: string,
    body: {
      rollback_id: string;
      target_finalization_id: string;
      reason: string;
      requested_by: string;
      apply_immediately?: boolean;
    },
  ): Promise<AisleRevisionDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/rollback`;
    return this.api.post<AisleRevisionDto>(path, body, { timeoutMs: 60_000 });
  }
}
