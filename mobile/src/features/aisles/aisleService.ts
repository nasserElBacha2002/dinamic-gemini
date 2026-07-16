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
    return canSelectAisle(aisle).ok;
  }
}

export interface SelectionDecision {
  readonly ok: boolean;
  readonly reason: string | null;
}

export function canSelectAisle(aisle: AisleDto): SelectionDecision {
  if (!aisle.is_active) {
    return { ok: false, reason: 'Pasillo inactivo.' };
  }
  const status = aisle.status.toLowerCase();
  if (status === 'created' || status === 'assets_uploaded' || status === 'failed') {
    return { ok: true, reason: null };
  }
  if (status === 'queued' || status === 'processing' || status === 'processed' || status === 'in_review' || status === 'completed') {
    return { ok: false, reason: `Pasillo no disponible para captura local (estado ${aisle.status}).` };
  }
  return { ok: false, reason: `Estado de pasillo desconocido: ${aisle.status}.` };
}

