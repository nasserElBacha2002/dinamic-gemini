import type {
  InventoryListQuery,
  LocalCatalogRepository,
} from '../../database/repositories/localCatalogRepository';
import type { ApiClient } from '../../services/api/apiClient';
import { ApiError, NETWORK_ERROR, REQUEST_TIMEOUT } from '../../services/api/apiClient';
import type {
  CreateInventoryRequestDto,
  InventoryListItemDto,
  InventoryResponseDto,
  PageDto,
} from '../../services/api/types';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { CatalogSyncCoordinator } from '../catalog/catalogSyncCoordinator';

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
  constructor(
    private readonly api: ApiClient,
    private readonly catalog?: LocalCatalogRepository,
    private readonly catalogSync?: CatalogSyncCoordinator,
    private readonly connectivity?: ConnectivityService,
  ) {}

  async listLocal(query: InventoryQuery = {}): Promise<PageDto<InventoryListItemDto>> {
    if (!this.catalog) {
      return emptyPage(query);
    }
    return this.catalog.listInventories(buildInventoryListQuery(query));
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

  async list(query: InventoryQuery = {}): Promise<PageDto<InventoryListItemDto>> {
    const local = await this.listLocal(query);
    if (this.shouldPreferLocal(local)) {
      if (this.connectivity?.getState() !== 'offline') {
        void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      }
      return local;
    }
    if (this.connectivity?.getState() === 'offline') {
      return local;
    }
    try {
      const remote = await this.fetchRemoteList(query);
      void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      return remote;
    } catch (e) {
      if (shouldFallbackToLocal(e) && local.total_items > 0) {
        return local;
      }
      throw e;
    }
  }

  async getById(inventoryId: string): Promise<InventoryListItemDto> {
    const localRow = await this.catalog?.getInventoryById(inventoryId);
    if (localRow && localRow.active === 1) {
      if (this.connectivity?.getState() !== 'offline') {
        void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      }
      return mapInventoryRow(localRow);
    }
    if (this.connectivity?.getState() === 'offline' && localRow) {
      return mapInventoryRow(localRow);
    }
    const created = await this.api.get<InventoryResponseDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}`,
    );
    try {
      const listed = await this.fetchRemoteList({ search: created.name, pageSize: 50 });
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

  private shouldPreferLocal(local: PageDto<InventoryListItemDto>): boolean {
    if (local.total_items > 0) {
      return true;
    }
    return this.connectivity?.getState() === 'offline';
  }

  private async fetchRemoteList(query: InventoryQuery): Promise<PageDto<InventoryListItemDto>> {
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

function emptyPage(query: InventoryQuery): PageDto<InventoryListItemDto> {
  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 25;
  return {
    items: [],
    page,
    page_size: pageSize,
    total_items: 0,
    total_pages: 1,
  };
}

function mapInventoryRow(row: {
  id: string;
  name: string;
  status: string;
  client_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  aisles_count: number;
  pending_review_count: number;
  last_activity_at: string | null;
  processing_mode: string;
}): InventoryListItemDto {
  return {
    id: row.id,
    name: row.name,
    status: row.status,
    client_id: row.client_id,
    created_at: row.created_at,
    updated_at: row.updated_at,
    aisles_count: row.aisles_count,
    pending_review_count: row.pending_review_count,
    last_activity_at: row.last_activity_at,
    processing_mode: row.processing_mode,
  };
}

function buildInventoryListQuery(query: InventoryQuery): InventoryListQuery {
  return {
    ...(query.search !== undefined ? { search: query.search } : {}),
    ...(query.page !== undefined ? { page: query.page } : {}),
    ...(query.pageSize !== undefined ? { pageSize: query.pageSize } : {}),
  };
}

function shouldFallbackToLocal(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return true;
  }
  if (error.status === null) {
    return error.code === NETWORK_ERROR || error.code === REQUEST_TIMEOUT;
  }
  return error.status >= 500;
}
