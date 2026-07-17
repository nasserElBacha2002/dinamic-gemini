import type { ApiClient } from '../../services/api/apiClient';
import type {
  SourceAssetDto,
  UploadAisleAssetsResponseDto,
} from '../../services/api/types';

export interface LocalUploadFile {
  readonly uri: string;
  readonly name: string;
  readonly mimeType: string;
}

export class AisleAssetsApi {
  constructor(private readonly api: ApiClient) {}

  async uploadBatch(input: {
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly uploadBatchId: string;
    readonly clientFileIds: readonly string[];
    readonly files: readonly LocalUploadFile[];
    readonly signal?: AbortSignal;
  }): Promise<UploadAisleAssetsResponseDto> {
    const form = new FormData();
    form.append('upload_batch_id', input.uploadBatchId);
    for (const id of input.clientFileIds) {
      form.append('client_file_ids', id);
    }
    for (const file of input.files) {
      form.append('files', {
        uri: file.uri,
        name: file.name,
        type: file.mimeType,
      } as unknown as Blob);
    }
    const path =
      `/api/v3/inventories/${encodeURIComponent(input.inventoryId)}` +
      `/aisles/${encodeURIComponent(input.aisleId)}/assets`;
    return this.api.postMultipart<UploadAisleAssetsResponseDto>(path, form, {
      ...(input.signal ? { signal: input.signal } : {}),
      timeoutMs: 120_000,
    });
  }

  async listAssets(inventoryId: string, aisleId: string): Promise<SourceAssetDto[]> {
    return this.api.get<SourceAssetDto[]>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets`,
    );
  }

  async deleteAsset(inventoryId: string, aisleId: string, assetId: string): Promise<void> {
    await this.api.delete(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}`,
    );
  }
}
