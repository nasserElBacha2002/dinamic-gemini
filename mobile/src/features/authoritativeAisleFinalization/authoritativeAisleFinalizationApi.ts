import type { ApiClient } from '../../services/api/apiClient';
import {
  mapAuthoritativeReadinessDto,
  type AuthoritativeAisleReadiness,
  type AuthoritativeAisleReadinessApiDto,
} from './authoritativeAisleReadiness';

export interface FinalizeAuthoritativeAisleRequest {
  readonly finalization_id: string;
  readonly expected_asset_count: number;
  readonly client_session_id: string | null;
}

export interface FinalizeAuthoritativeAisleResponse {
  readonly finalization_id: string;
  readonly status: string;
  readonly aisle_status: string;
  readonly total_assets: number;
  readonly applied_assets: number;
  readonly excluded_assets: number;
  readonly position_count: number;
  readonly idempotent_replay: boolean;
}

export class AuthoritativeAisleFinalizationApi {
  constructor(private readonly api: ApiClient) {}

  async getReadiness(
    inventoryId: string,
    aisleId: string,
  ): Promise<AuthoritativeAisleReadiness> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/authoritative-readiness`;
    const dto = await this.api.get<AuthoritativeAisleReadinessApiDto>(path, {
      timeoutMs: 15_000,
    });
    return mapAuthoritativeReadinessDto(dto);
  }

  async recordExclusion(
    inventoryId: string,
    aisleId: string,
    assetId: string,
    reason: string,
  ): Promise<void> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}` +
      `/assets/${encodeURIComponent(assetId)}/authoritative-exclusion`;
    await this.api.post(path, { reason }, { timeoutMs: 15_000 });
  }

  async finalize(
    inventoryId: string,
    aisleId: string,
    body: FinalizeAuthoritativeAisleRequest,
  ): Promise<FinalizeAuthoritativeAisleResponse> {
    const path =
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}` +
      `/aisles/${encodeURIComponent(aisleId)}/finalize-authoritative`;
    return this.api.post<FinalizeAuthoritativeAisleResponse>(path, body, {
      timeoutMs: 60_000,
    });
  }
}
