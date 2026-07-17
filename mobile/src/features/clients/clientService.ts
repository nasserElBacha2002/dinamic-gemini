import type { ApiClient } from '../../services/api/apiClient';
import type { ClientDto, ClientSupplierDto, PageDto } from '../../services/api/types';

export interface ClientQuery {
  readonly page?: number;
  readonly pageSize?: number;
}

export class ClientService {
  constructor(private readonly api: ApiClient) {}

  async list(query: ClientQuery = {}): Promise<PageDto<ClientDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 100),
    });
    return this.api.get<PageDto<ClientDto>>(`/api/v3/clients/?${params.toString()}`);
  }

  async listSuppliers(clientId: string, query: ClientQuery = {}): Promise<PageDto<ClientSupplierDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 200),
    });
    return this.api.get<PageDto<ClientSupplierDto>>(
      `/api/v3/clients/${encodeURIComponent(clientId)}/suppliers?${params.toString()}`,
    );
  }
}
