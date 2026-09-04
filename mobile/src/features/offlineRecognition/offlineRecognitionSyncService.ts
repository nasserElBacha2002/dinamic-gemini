import type { ApiClient } from '../../services/api/apiClient';
import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';
import type { LocalLabelProfileResolver } from './localLabelProfileResolver';
import type { OfflineRecognitionBundleDto } from './types';
import { assertCompatibleBundle, IncompatibleOfflineBundleError } from './types';

export class OfflineRecognitionSyncService {
  constructor(
    private readonly api: ApiClient,
    private readonly repo: OfflineRecognitionConfigRepository,
    private readonly resolver?: LocalLabelProfileResolver,
  ) {}

  async fetchBundle(inventoryId: string): Promise<OfflineRecognitionBundleDto> {
    return this.api.get<OfflineRecognitionBundleDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/recognition-config`,
    );
  }

  /**
   * Download + atomically persist. On failure previous SQLite bundle is preserved.
   */
  async syncInventory(inventoryId: string): Promise<{
    ok: boolean;
    syncedAt: string | null;
    errorCode?: string;
    skippedSameRevision?: boolean;
  }> {
    try {
      const existing = await this.repo.getSyncMeta(inventoryId);
      const bundle = await this.fetchBundle(inventoryId);
      assertCompatibleBundle(bundle);
      if (
        existing?.bundle_revision &&
        bundle.bundle_revision &&
        existing.bundle_revision === bundle.bundle_revision
      ) {
        return {
          ok: true,
          syncedAt: existing.synced_at,
          skippedSameRevision: true,
        };
      }
      const syncedAt = new Date().toISOString();
      await this.repo.replaceBundle(bundle, syncedAt);
      this.resolver?.invalidate();
      return { ok: true, syncedAt };
    } catch (e) {
      if (e instanceof IncompatibleOfflineBundleError) {
        return { ok: false, syncedAt: null, errorCode: e.code };
      }
      return {
        ok: false,
        syncedAt: null,
        errorCode: e instanceof Error ? e.message.slice(0, 80) : 'SYNC_FAILED',
      };
    }
  }
}
