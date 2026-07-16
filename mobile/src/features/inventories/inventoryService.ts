import type { ApiClient } from '../../services/api/apiClient';
import type { InventoryListItemDto, PageDto } from '../../services/api/types';

export interface InventoryQuery {
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
}

export class InventoryService {
  constructor(private readonly api: ApiClient) {}

  async list(query: InventoryQuery = {}): Promise<PageDto<InventoryListItemDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 25),
      sort_by: 'created_at',
      sort_dir: 'desc',
    });
    if (query.search?.trim()) {
      params.set('search', query.search.trim());
    }
    return this.api.get<PageDto<InventoryListItemDto>>(`/api/v3/inventories/?${params.toString()}`);
  }

  canSelect(inventory: InventoryListItemDto): boolean {
    return !['closed', 'archived', 'cancelled'].includes(inventory.status.toLowerCase());
  }
}

