import type { ApiClient } from '../../services/api/apiClient';
import { ApiError } from '../../services/api/apiClient';
import type {
  CreateInventoryRequestDto,
  InventoryListItemDto,
  InventoryResponseDto,
  PageDto,
} from '../../services/api/types';

export interface InventoryQuery {
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
}

export interface CreateInventoryInput {
  readonly name: string;
  readonly clientId: string;
  readonly processingMode?: 'production' | 'test';
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

  async create(input: CreateInventoryInput): Promise<InventoryListItemDto> {
    const name = input.name.trim();
    if (!name) {
      throw new Error('El nombre del inventario es obligatorio.');
    }
    if (name.length > 255) {
      throw new Error('El nombre del inventario supera el máximo permitido (255).');
    }
    const clientId = input.clientId.trim();
    if (!clientId) {
      throw new Error('Seleccioná un cliente.');
    }
    const body: CreateInventoryRequestDto = {
      name,
      client_id: clientId,
      processing_mode: input.processingMode ?? 'production',
    };
    try {
      const created = await this.api.post<InventoryResponseDto>('/api/v3/inventories/', body);
      try {
        return await this.getById(created.id);
      } catch {
        return inventoryResponseToListItem(created);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        throw new Error('No tenés permisos para realizar esta acción.');
      }
      throw e;
    }
  }

  async getById(inventoryId: string): Promise<InventoryListItemDto> {
    const created = await this.api.get<InventoryResponseDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}`,
    );
    try {
      const listed = await this.list({ search: created.name, pageSize: 50 });
      const match = listed.items.find((i) => i.id === inventoryId);
      if (match) return match;
    } catch {
      // fall through to thin response
    }
    return inventoryResponseToListItem(created);
  }

  canSelect(_inventory?: InventoryListItemDto): boolean {
    return true;
  }
}

export function inventoryResponseToListItem(created: InventoryResponseDto): InventoryListItemDto {
  return {
    id: created.id,
    name: created.name,
    status: created.status,
    client_id: created.client_id,
    created_at: created.created_at,
    updated_at: created.updated_at,
    aisles_count: 0,
    pending_review_count: 0,
    last_activity_at: created.updated_at ?? created.created_at,
    processing_mode: created.processing_mode ?? 'production',
  };
}

export interface SelectionDecision {
  readonly ok: true;
  readonly reason: null;
}

/** Inventory selection is always allowed; remote status is informational only. */
export function canSelectInventory(_inventory?: InventoryListItemDto): SelectionDecision {
  return { ok: true, reason: null };
}

