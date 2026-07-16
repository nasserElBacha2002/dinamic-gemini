import type { ApiClient } from '../../services/api/apiClient';
import type { AisleDto, PageDto } from '../../services/api/types';

export interface AisleQuery {
  readonly inventoryId: string;
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
}

export class AisleService {
  constructor(private readonly api: ApiClient) {}

  async list(query: AisleQuery): Promise<PageDto<AisleDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 50),
      sort_by: 'code',
      sort_dir: 'asc',
    });
    if (query.search?.trim()) {
      params.set('search', query.search.trim());
    }
    return this.api.get<PageDto<AisleDto>>(
      `/api/v3/inventories/${encodeURIComponent(query.inventoryId)}/aisles?${params.toString()}`,
    );
  }

  canSelect(aisle: AisleDto): boolean {
    return aisle.is_active && !['processing'].includes(aisle.status.toLowerCase());
  }
}

