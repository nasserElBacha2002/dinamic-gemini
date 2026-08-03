import type { ApiClient } from '../../services/api/apiClient';
import type { OrderedCaptureSessionDto } from '../../services/api/types';

export class OrderedCaptureApi {
  constructor(private readonly api: ApiClient) {}

  async createSession(inventoryId: string, aisleId: string): Promise<OrderedCaptureSessionDto> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/ordered-capture-sessions`;
    return this.api.post<OrderedCaptureSessionDto>(path, {});
  }

  async sealSession(
    orderedCaptureSessionId: string,
    body: { readonly expected_asset_count: number; readonly sequence_version: number },
  ): Promise<OrderedCaptureSessionDto> {
    // Mounted under inventories router: /api/v3/inventories/ordered-capture-sessions/{id}/seal
    const path =
      `/api/v3/inventories/ordered-capture-sessions/` +
      `${encodeURIComponent(orderedCaptureSessionId)}/seal`;
    return this.api.post<OrderedCaptureSessionDto>(path, body);
  }
}
