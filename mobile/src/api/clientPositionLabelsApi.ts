import type { ApiClient } from '../services/api/apiClient';

export type ClientPositionLabelDto = {
  id: string;
  public_identifier: string;
  client_id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ClientPositionLabelListDto = {
  items: ClientPositionLabelDto[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export interface ClientPositionLabelQuery {
  readonly search?: string;
  readonly status?: string;
  readonly page?: number;
  readonly pageSize?: number;
}

/**
 * Client-scoped positioning labels — list/get only (no local QR/signing).
 * Does not require an inventory or aisle selection.
 */
export class ClientPositionLabelService {
  constructor(private readonly api: ApiClient) {}

  async list(
    clientId: string,
    query: ClientPositionLabelQuery = {}
  ): Promise<ClientPositionLabelListDto> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 100),
    });
    if (query.search) params.set('search', query.search);
    if (query.status) params.set('status', query.status);
    return this.api.get<ClientPositionLabelListDto>(
      `/api/v3/clients/${encodeURIComponent(clientId)}/position-labels?${params.toString()}`
    );
  }

  async get(clientId: string, labelId: string): Promise<ClientPositionLabelDto> {
    return this.api.get<ClientPositionLabelDto>(
      `/api/v3/clients/${encodeURIComponent(clientId)}/position-labels/${encodeURIComponent(labelId)}`
    );
  }
}

/** Future inventory scan contract (not implemented — detection phase deferred):
 * QR → label_id → resolve label → validate client_id + ACTIVE → use name as current position.
 */
export const FUTURE_POSITION_LABEL_SCAN_CONTRACT = {
  type: 'DINAMIC_POSITION',
  resolve: 'label_id → client_position_labels',
  ownership: 'client-scoped (not inventory-owned)',
} as const;
