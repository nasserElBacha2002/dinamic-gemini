import type { Logger } from '../../core/logging';
import { emitObservability } from '../../observability/emitHelpers';
import type { ObservabilityReporter } from '../../observability/types';
import type {
  LocalCatalogRepository,
  CatalogSnapshot,
} from '../../database/repositories/localCatalogRepository';
import type { ApiClient } from '../../services/api/apiClient';
import type {
  AisleDto,
  ClientSupplierDto,
  InventoryListItemDto,
  PageDto,
} from '../../services/api/types';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { OfflineRecognitionSyncService } from '../offlineRecognition/offlineRecognitionSyncService';
import { normalizeAisleDto } from '../aisles/aisleService';
import { computeCatalogRevision } from './catalogRevision';
import type { CatalogSyncStatus, CatalogSyncTrigger } from './catalogSyncPolicy';

export interface RecognitionSyncFailure {
  readonly inventoryId: string;
  readonly errorCode?: string;
}

export interface CatalogSyncOptions {
  readonly trigger?: CatalogSyncTrigger;
}

export interface CatalogSyncResult {
  readonly ok: boolean;
  readonly status: CatalogSyncStatus;
  readonly trigger?: CatalogSyncTrigger;
  readonly syncedAt: string | null;
  readonly catalogChanged: boolean;
  readonly catalogSkippedSameRevision: boolean;
  readonly recognitionSyncedCount: number;
  readonly recognitionSkippedCount: number;
  readonly recognitionFailures: readonly RecognitionSyncFailure[];
  readonly errorCode?: string;
  readonly inventoryCount?: number;
  readonly supplierCount?: number;
  readonly aisleCount?: number;
  readonly catalogRevision?: string | null;
  readonly durationMs?: number;
}

export interface CatalogHydrationSummary {
  readonly inventoryCount: number;
  readonly supplierCount: number;
  readonly profileCount: number;
  readonly catalogRevision: string | null;
  readonly lastSyncedAt: string | null;
}

export class CatalogSyncService {
  private syncInFlight: Promise<CatalogSyncResult> | null = null;

  constructor(
    private readonly api: ApiClient,
    private readonly catalog: LocalCatalogRepository,
    private readonly connectivity: ConnectivityService,
    private readonly logger: Logger,
    private readonly recognitionSync: OfflineRecognitionSyncService,
    private readonly reporter?: ObservabilityReporter | null,
  ) {}

  async hydrateSummary(): Promise<CatalogHydrationSummary> {
    const meta = await this.catalog.getSyncMeta();
    return {
      inventoryCount: await this.catalog.countActiveInventories(),
      supplierCount: await this.catalog.countActiveSuppliers(),
      profileCount: await this.catalog.countProfiles(),
      catalogRevision: meta?.catalog_revision ?? null,
      lastSyncedAt: meta?.last_successful_sync_at ?? meta?.last_synced_at ?? null,
    };
  }

  async bootstrapHydrate(mode: 'offline' | 'online' | 'unknown'): Promise<CatalogHydrationSummary> {
    const summary = await this.hydrateSummary();
    this.logger.info('recovery', {
      where: 'mobile_catalog_hydrated',
      mode,
      inventories: summary.inventoryCount,
      suppliers: summary.supplierCount,
      profiles: summary.profileCount,
      revision: summary.catalogRevision,
    });
    emitObservability(this.reporter, {
      name: 'mobile.catalog.hydrated',
      attributes: {
        startup_mode: mode,
        inventory_count: summary.inventoryCount,
        supplier_count: summary.supplierCount,
        profile_count: summary.profileCount,
        catalog_revision: summary.catalogRevision ?? '',
        last_synced_at: summary.lastSyncedAt ?? '',
      },
    });
    if (mode === 'offline') {
      emitObservability(this.reporter, {
        name: 'mobile.catalog.offline_start',
        attributes: {
          inventory_count: summary.inventoryCount,
          supplier_count: summary.supplierCount,
          profile_count: summary.profileCount,
        },
      });
    }
    return summary;
  }

  async syncCatalog(options: CatalogSyncOptions = {}): Promise<CatalogSyncResult> {
    if (this.syncInFlight) {
      return this.syncInFlight;
    }
    if (this.connectivity.getState() === 'offline') {
      return {
        ok: false,
        status: 'SKIPPED_OFFLINE',
        ...(options.trigger ? { trigger: options.trigger } : {}),
        syncedAt: null,
        catalogChanged: false,
        catalogSkippedSameRevision: false,
        recognitionSyncedCount: 0,
        recognitionSkippedCount: 0,
        recognitionFailures: [],
        errorCode: 'OFFLINE',
      };
    }
    this.syncInFlight = this.syncCatalogInner(options).finally(() => {
      this.syncInFlight = null;
    });
    return this.syncInFlight;
  }

  private async syncCatalogInner(options: CatalogSyncOptions): Promise<CatalogSyncResult> {
    const startedAt = Date.now();
    const attemptAtIso = new Date(startedAt).toISOString();
    await this.catalog.recordSyncAttempt(attemptAtIso).catch(() => undefined);

    emitObservability(this.reporter, {
      name: 'mobile.catalog.sync_started',
      attributes: { trigger: options.trigger ?? '' },
    });

    try {
      const remote = await this.fetchRemoteCatalog();
      emitObservability(this.reporter, {
        name: 'mobile.catalog.remote_fetched',
        attributes: {
          inventory_count: remote.inventories.length,
          supplier_count: remote.suppliers.length,
          aisle_count: remote.aisles.length,
          catalog_revision: remote.revision,
        },
      });

      const existing = await this.catalog.getSyncMeta();
      const catalogChanged =
        !existing?.catalog_revision || existing.catalog_revision !== remote.revision;

      let catalogSnapshotSyncedAt = existing?.last_synced_at ?? null;
      if (catalogChanged) {
        catalogSnapshotSyncedAt = new Date().toISOString();
        await this.catalog.replaceCatalogSnapshot(remote, catalogSnapshotSyncedAt);
        emitObservability(this.reporter, {
          name: 'mobile.catalog.snapshot_replaced',
          attributes: {
            catalog_revision: remote.revision,
            inventory_count: remote.inventories.length,
            supplier_count: remote.suppliers.length,
            aisle_count: remote.aisles.length,
          },
        });
      } else {
        emitObservability(this.reporter, {
          name: 'mobile.catalog.sync_no_changes',
          attributes: { catalog_revision: remote.revision },
        });
      }

      const recognitionResults = await this.syncRecognitionForInventories(remote.inventories);
      const recognitionFailures = recognitionResults.filter((result) => !result.ok);
      const recognitionSyncedCount = recognitionResults.filter(
        (result) => result.ok && !result.skippedSameRevision,
      ).length;
      const recognitionSkippedCount = recognitionResults.filter(
        (result) => result.ok && result.skippedSameRevision,
      ).length;
      const durationMs = Date.now() - startedAt;
      const status = deriveSyncStatus({
        catalogChanged,
        recognitionFailures: recognitionFailures.length,
        recognitionSyncedCount,
        recognitionSkippedCount,
        inventoryCount: remote.inventories.length,
      });
      const ok = status === 'SUCCESS' || status === 'NO_CHANGES';

      if (status === 'PARTIAL') {
        emitObservability(this.reporter, {
          name: 'mobile.catalog.sync_partial',
          attributes: {
            recognition_failure_count: recognitionFailures.length,
            recognition_success_count: recognitionSyncedCount + recognitionSkippedCount,
            duration_ms: durationMs,
          },
        });
        this.logger.warn('recovery', {
          where: 'catalog_sync_recognition_partial',
          failures: recognitionFailures.map((failure) => failure.inventoryId).join(','),
        });
      }

      emitObservability(this.reporter, {
        name:
          status === 'SUCCESS' || status === 'NO_CHANGES'
            ? 'mobile.catalog.sync_completed'
            : 'mobile.catalog.sync_failed',
        attributes: {
          status,
          catalog_changed: catalogChanged,
          catalog_skipped_same_revision: !catalogChanged,
          inventory_count: remote.inventories.length,
          supplier_count: remote.suppliers.length,
          aisle_count: remote.aisles.length,
          catalog_revision: remote.revision,
          last_synced_at: catalogSnapshotSyncedAt ?? '',
          recognition_synced_count: recognitionSyncedCount,
          recognition_skipped_count: recognitionSkippedCount,
          recognition_failure_count: recognitionFailures.length,
          duration_ms: durationMs,
        },
      });

      const syncCompletedAt =
        status === 'SUCCESS' || status === 'NO_CHANGES' ? new Date().toISOString() : null;
      await this.catalog
        .recordSyncResult({
          status,
          attemptAtIso,
          successfulAtIso: syncCompletedAt,
        })
        .catch(() => undefined);

      return {
        ok,
        status,
        ...(options.trigger ? { trigger: options.trigger } : {}),
        syncedAt: syncCompletedAt,
        catalogChanged,
        catalogSkippedSameRevision: !catalogChanged,
        recognitionSyncedCount,
        recognitionSkippedCount,
        recognitionFailures: recognitionFailures.map((failure) => ({
          inventoryId: failure.inventoryId,
          ...(failure.errorCode ? { errorCode: failure.errorCode } : {}),
        })),
        ...(status === 'PARTIAL'
          ? { errorCode: 'RECOGNITION_PARTIAL_FAILURE' }
          : status === 'FAILED'
            ? { errorCode: 'SYNC_FAILED' }
            : {}),
        catalogRevision: remote.revision,
        inventoryCount: remote.inventories.length,
        supplierCount: remote.suppliers.length,
        aisleCount: remote.aisles.length,
        durationMs,
      };
    } catch (e) {
      const errorCode = e instanceof Error ? e.message.slice(0, 80) : 'SYNC_FAILED';
      const durationMs = Date.now() - startedAt;
      this.logger.warn('recovery', { where: 'catalog_sync', message: String(e) });
      emitObservability(this.reporter, {
        name: 'mobile.catalog.sync_failed',
        attributes: { error_code: errorCode, duration_ms: durationMs },
      });
      await this.catalog
        .recordSyncResult({
          status: 'FAILED',
          attemptAtIso,
          successfulAtIso: null,
        })
        .catch(() => undefined);
      return {
        ok: false,
        status: 'FAILED',
        ...(options.trigger ? { trigger: options.trigger } : {}),
        syncedAt: null,
        catalogChanged: false,
        catalogSkippedSameRevision: false,
        recognitionSyncedCount: 0,
        recognitionSkippedCount: 0,
        recognitionFailures: [],
        errorCode,
        durationMs,
      };
    }
  }

  private async syncRecognitionForInventories(
    inventories: readonly InventoryListItemDto[],
  ): Promise<
    readonly {
      inventoryId: string;
      ok: boolean;
      skippedSameRevision?: boolean;
      errorCode?: string;
    }[]
  > {
    const results: {
      inventoryId: string;
      ok: boolean;
      skippedSameRevision?: boolean;
      errorCode?: string;
    }[] = [];
    for (const inventory of inventories) {
      emitObservability(this.reporter, {
        name: 'mobile.recognition.sync_started',
        attributes: { inventory_id: inventory.id },
      });
      try {
        const result = await this.recognitionSync.syncInventory(inventory.id);
        if (result.skippedSameRevision) {
          emitObservability(this.reporter, {
            name: 'mobile.recognition.sync_skipped',
            attributes: { inventory_id: inventory.id },
          });
        } else if (result.ok) {
          emitObservability(this.reporter, {
            name: 'mobile.recognition.sync_completed',
            attributes: { inventory_id: inventory.id },
          });
        } else {
          emitObservability(this.reporter, {
            name: 'mobile.recognition.sync_failed',
            attributes: {
              inventory_id: inventory.id,
              error_code: result.errorCode ?? 'SYNC_FAILED',
            },
          });
        }
        results.push({
          inventoryId: inventory.id,
          ok: result.ok,
          ...(result.skippedSameRevision ? { skippedSameRevision: true } : {}),
          ...(result.errorCode ? { errorCode: result.errorCode } : {}),
        });
      } catch (e) {
        emitObservability(this.reporter, {
          name: 'mobile.recognition.sync_failed',
          attributes: {
            inventory_id: inventory.id,
            error_code: e instanceof Error ? e.message.slice(0, 80) : 'RECOGNITION_SYNC_FAILED',
          },
        });
        results.push({
          inventoryId: inventory.id,
          ok: false,
          errorCode: e instanceof Error ? e.message.slice(0, 80) : 'RECOGNITION_SYNC_FAILED',
        });
      }
    }
    return results;
  }

  private async fetchRemoteCatalog(): Promise<CatalogSnapshot> {
    const inventories = await fetchAllPages((page) =>
      this.api.get<PageDto<InventoryListItemDto>>(
        `/api/v3/inventories/?${inventoryListParams(page).toString()}`,
      ),
    );
    const aisles: AisleDto[] = [];
    for (const inv of inventories) {
      const invAisles = await fetchAllPages((page) =>
        this.api
          .get<PageDto<unknown>>(
            `/api/v3/inventories/${encodeURIComponent(inv.id)}/aisles?${aisleListParams(page).toString()}`,
          )
          .then((raw) => ({
            ...raw,
            items: (raw.items ?? []).map((item) => normalizeAisleDto(item)),
          })),
      );
      aisles.push(...invAisles);
    }
    const clientIds = [...new Set(inventories.map((i) => i.client_id).filter(Boolean))] as string[];
    const suppliers: ClientSupplierDto[] = [];
    for (const clientId of clientIds) {
      const clientSuppliers = await fetchAllPages((page) =>
        this.api.get<PageDto<ClientSupplierDto>>(
          `/api/v3/clients/${encodeURIComponent(clientId)}/suppliers?${supplierListParams(page).toString()}`,
        ),
      );
      suppliers.push(...clientSuppliers);
    }
    const revision = computeCatalogRevision({
      inventories: inventories.map((inv) => ({
        id: inv.id,
        client_id: inv.client_id,
        name: inv.name,
        status: inv.status,
        updated_at: inv.updated_at,
        processing_mode: inv.processing_mode,
      })),
      aisles: aisles.map((aisle) => ({
        id: aisle.id,
        inventory_id: aisle.inventory_id,
        code: aisle.code,
        status: aisle.status,
        updated_at: aisle.updated_at,
        is_active: aisle.is_active ?? true,
      })),
      suppliers: suppliers.map((supplier) => ({
        id: supplier.id,
        client_id: supplier.client_id,
        name: supplier.name,
        status: supplier.status,
        updated_at: supplier.updated_at,
      })),
    });
    return { inventories, aisles, suppliers, revision };
  }
}

function deriveSyncStatus(input: {
  readonly catalogChanged: boolean;
  readonly recognitionFailures: number;
  readonly recognitionSyncedCount: number;
  readonly recognitionSkippedCount: number;
  readonly inventoryCount: number;
}): CatalogSyncStatus {
  if (input.recognitionFailures > 0) {
    return 'PARTIAL';
  }
  if (!input.catalogChanged && input.recognitionSyncedCount === 0) {
    if (input.inventoryCount === 0 || input.recognitionSkippedCount >= input.inventoryCount) {
      return 'NO_CHANGES';
    }
  }
  return 'SUCCESS';
}

async function fetchAllPages<T>(
  fetchPage: (page: number) => Promise<PageDto<T>>,
): Promise<T[]> {
  const all: T[] = [];
  let page = 1;
  let totalPages = 1;
  while (page <= totalPages) {
    const res = await fetchPage(page);
    all.push(...(res.items ?? []));
    totalPages = Math.max(1, res.total_pages);
    page += 1;
  }
  return all;
}

function inventoryListParams(page: number): URLSearchParams {
  return new URLSearchParams({
    page: String(page),
    page_size: '100',
    sort_by: 'created_at',
    sort_dir: 'desc',
  });
}

function aisleListParams(page: number): URLSearchParams {
  return new URLSearchParams({
    page: String(page),
    page_size: '100',
    sort_by: 'code',
    sort_dir: 'asc',
  });
}

function supplierListParams(page: number): URLSearchParams {
  return new URLSearchParams({
    page: String(page),
    page_size: '200',
  });
}
