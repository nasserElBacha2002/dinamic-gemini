import type {
  LocalCatalogRepository,
  SupplierListQuery,
} from '../../database/repositories/localCatalogRepository';
import type { ApiClient } from '../../services/api/apiClient';
import { ApiError, NETWORK_ERROR, REQUEST_TIMEOUT } from '../../services/api/apiClient';
import type { ClientDto, ClientSupplierDto, PageDto } from '../../services/api/types';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { CatalogSyncCoordinator } from '../catalog/catalogSyncCoordinator';

export interface ClientQuery {
  readonly page?: number;
  readonly pageSize?: number;
}

export class ClientService {
  constructor(
    private readonly api: ApiClient,
    private readonly catalog?: LocalCatalogRepository,
    private readonly catalogSync?: CatalogSyncCoordinator,
    private readonly connectivity?: ConnectivityService,
  ) {}

  async list(query: ClientQuery = {}): Promise<PageDto<ClientDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 100),
    });
    return this.api.get<PageDto<ClientDto>>(`/api/v3/clients/?${params.toString()}`);
  }

  async listSuppliersLocal(
    clientId: string,
    query: ClientQuery = {},
  ): Promise<PageDto<ClientSupplierDto>> {
    if (!this.catalog) {
      return emptyPage(query);
    }
    return this.catalog.listSuppliers(buildSupplierListQuery(clientId, query));
  }

  async listSuppliers(clientId: string, query: ClientQuery = {}): Promise<PageDto<ClientSupplierDto>> {
    const local = await this.listSuppliersLocal(clientId, query);
    if (local.total_items > 0 || this.connectivity?.getState() === 'offline') {
      if (this.connectivity?.getState() !== 'offline') {
        void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      }
      return local;
    }
    try {
      const remote = await this.fetchRemoteSuppliers(clientId, query);
      void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      return remote;
    } catch (e) {
      if (shouldFallbackToLocal(e) && local.total_items > 0) {
        return local;
      }
      throw e;
    }
  }

  private async fetchRemoteSuppliers(
    clientId: string,
    query: ClientQuery,
  ): Promise<PageDto<ClientSupplierDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 200),
    });
    return this.api.get<PageDto<ClientSupplierDto>>(
      `/api/v3/clients/${encodeURIComponent(clientId)}/suppliers?${params.toString()}`,
    );
  }
}

function emptyPage(query: ClientQuery): PageDto<ClientSupplierDto> {
  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 200;
  return {
    items: [],
    page,
    page_size: pageSize,
    total_items: 0,
    total_pages: 1,
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

function buildSupplierListQuery(clientId: string, query: ClientQuery): SupplierListQuery {
  return {
    clientId,
    ...(query.page !== undefined ? { page: query.page } : {}),
    ...(query.pageSize !== undefined ? { pageSize: query.pageSize } : {}),
  };
}
