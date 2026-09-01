import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
import type {
  CatalogSyncService,
  CatalogSyncResult,
  CatalogHydrationSummary,
} from './catalogSyncService';
import type { CatalogSyncTrigger } from './catalogSyncPolicy';
import {
  isAutoSyncThrottled,
  shouldBypassSyncThrottle,
} from './catalogSyncPolicy';

export interface CatalogSyncRequestOptions {
  readonly force?: boolean;
}

/** Unified entry point for all catalog sync triggers (single-flight + throttling). */
export class CatalogSyncCoordinator {
  private lastSuccessfulSyncAtMs: number | null = null;

  constructor(
    private readonly syncService: CatalogSyncService,
    private readonly connectivity: ConnectivityService,
    private readonly catalogRepo: LocalCatalogRepository,
  ) {}

  async initialize(): Promise<void> {
    const meta = await this.catalogRepo.getSyncMeta();
    const ts = meta?.last_successful_sync_at ?? meta?.last_synced_at;
    if (ts) {
      const parsed = Date.parse(ts);
      if (!Number.isNaN(parsed)) {
        this.lastSuccessfulSyncAtMs = parsed;
      }
    }
  }

  async hydrateSummary(): Promise<CatalogHydrationSummary> {
    return this.syncService.hydrateSummary();
  }

  async bootstrap(mode: 'offline' | 'online' | 'unknown'): Promise<CatalogHydrationSummary> {
    const summary = await this.syncService.bootstrapHydrate(mode);
    if (mode !== 'offline') {
      void this.requestSync('bootstrap').catch(() => undefined);
    }
    return summary;
  }

  requestSync(
    trigger: CatalogSyncTrigger,
    options?: CatalogSyncRequestOptions,
  ): Promise<CatalogSyncResult> {
    if (this.connectivity.getState() === 'offline') {
      if (trigger !== 'manual') {
        return Promise.resolve(skippedOffline(trigger));
      }
    }
    const nowMs = Date.now();
    if (
      !shouldBypassSyncThrottle(trigger, options?.force) &&
      isAutoSyncThrottled(this.lastSuccessfulSyncAtMs, nowMs)
    ) {
      return Promise.resolve(skippedThrottle(trigger));
    }
    return this.syncService.syncCatalog({ trigger }).then((result) => {
      this.applyResultTimestamps(result);
      return result;
    });
  }

  /** Manual sync — bypasses throttle, respects single-flight. */
  syncManual(): Promise<CatalogSyncResult> {
    return this.requestSync('manual', { force: true });
  }

  /** Backward-compatible alias for manual sync. */
  syncCatalog(): Promise<CatalogSyncResult> {
    return this.syncManual();
  }

  private applyResultTimestamps(result: CatalogSyncResult): void {
    if (result.status === 'SUCCESS' || result.status === 'NO_CHANGES') {
      if (result.syncedAt) {
        const parsed = Date.parse(result.syncedAt);
        if (!Number.isNaN(parsed)) {
          this.lastSuccessfulSyncAtMs = parsed;
          return;
        }
      }
      this.lastSuccessfulSyncAtMs = Date.now();
    }
  }
}

function skippedOffline(trigger: CatalogSyncTrigger): CatalogSyncResult {
  return {
    ok: false,
    status: 'SKIPPED_OFFLINE',
    trigger,
    syncedAt: null,
    catalogChanged: false,
    catalogSkippedSameRevision: false,
    recognitionSyncedCount: 0,
    recognitionSkippedCount: 0,
    recognitionFailures: [],
    errorCode: 'OFFLINE',
  };
}

function skippedThrottle(trigger: CatalogSyncTrigger): CatalogSyncResult {
  return {
    ok: true,
    status: 'SKIPPED_THROTTLE',
    trigger,
    syncedAt: null,
    catalogChanged: false,
    catalogSkippedSameRevision: false,
    recognitionSyncedCount: 0,
    recognitionSkippedCount: 0,
    recognitionFailures: [],
  };
}
