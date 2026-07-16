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
    return canSelectInventory(inventory).ok;
  }
}

export interface SelectionDecision {
  readonly ok: boolean;
  readonly reason: string | null;
}

export function canSelectInventory(inventory: InventoryListItemDto): SelectionDecision {
  const status = inventory.status.toLowerCase();
  if (status === 'draft' || status === 'failed') {
    return { ok: true, reason: null };
  }
  if (status === 'processing' || status === 'in_review' || status === 'completed') {
    return { ok: false, reason: `Inventario no disponible para captura local (estado ${inventory.status}).` };
  }
  return { ok: false, reason: `Estado de inventario desconocido: ${inventory.status}.` };
}

