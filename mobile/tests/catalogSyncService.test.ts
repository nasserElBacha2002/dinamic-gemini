import { createLogger } from '../src/core/logging';
import { computeCatalogRevision } from '../src/features/catalog/catalogRevision';
import { CatalogSyncCoordinator } from '../src/features/catalog/catalogSyncCoordinator';
import { CATALOG_AUTO_SYNC_MIN_INTERVAL_MS } from '../src/features/catalog/catalogSyncPolicy';
import type { LocalCatalogRepository } from '../src/database/repositories/localCatalogRepository';
import { CatalogSyncService } from '../src/features/catalog/catalogSyncService';
import type { OfflineRecognitionSyncService } from '../src/features/offlineRecognition/offlineRecognitionSyncService';
import type { ConnectivityService } from '../src/services/connectivity/connectivity';

function createNoOpRecognitionSync(): OfflineRecognitionSyncService {
  return {
    syncInventory: jest.fn(async () => ({
      ok: true,
      syncedAt: '2026-01-01T00:00:00Z',
      skippedSameRevision: true,
    })),
    fetchBundle: jest.fn(),
  } as unknown as OfflineRecognitionSyncService;
}

function sampleInventory(id: string, clientId = 'client-1') {
  return {
    id,
    name: `Inventory ${id}`,
    status: 'active',
    client_id: clientId,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    aisles_count: 1,
    pending_review_count: 0,
    last_activity_at: '2026-01-02T00:00:00Z',
    processing_mode: 'production',
  };
}

function buildRemoteFixture(
  inventoryIds: string[],
  extraSuppliers: ReturnType<typeof sampleSupplier>[] = [],
) {
  const inventories = inventoryIds.map((id) => sampleInventory(id));
  const aisles = inventoryIds.map((id) => ({
    id: `aisle-${id}`,
    inventory_id: id,
    code: 'A01',
    status: 'created',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    is_active: true,
    assets_count: 0,
    positions_count: 0,
    pending_review_positions_count: 0,
    client_supplier_id: 'sup-b' as string | null,
  }));
  const suppliers = [
    {
      id: 'sup-1',
      client_id: 'client-1',
      name: 'Supplier',
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    ...extraSuppliers,
  ];
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
      is_active: aisle.is_active,
      client_supplier_id: aisle.client_supplier_id,
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

function sampleSupplier(id: string, name: string) {
  return {
    id,
    client_id: 'client-1',
    name,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function createApiMock(fixture: ReturnType<typeof buildRemoteFixture>, options?: { pages?: number }) {
  const inventoryPages = options?.pages ?? 1;
  return {
    get: jest.fn(async (path: string) => {
      if (path.startsWith('/api/v3/inventories/?')) {
        const url = new URL(path, 'https://example.test');
        const page = Number(url.searchParams.get('page') ?? '1');
        if (inventoryPages > 1) {
          const pageSize = 100;
          const all = fixture.inventories;
          const start = (page - 1) * pageSize;
          const items = all.slice(start, start + pageSize);
          return {
            items,
            page,
            page_size: pageSize,
            total_items: all.length,
            total_pages: inventoryPages,
          };
        }
        return {
          items: fixture.inventories,
          page: 1,
          page_size: 100,
          total_items: fixture.inventories.length,
          total_pages: 1,
        };
      }
      if (path.includes('/aisles')) {
        const inventoryId = path.match(/inventories\/([^/]+)\/aisles/)?.[1];
        const items = fixture.aisles.filter((aisle) => aisle.inventory_id === inventoryId);
        return {
          items,
          page: 1,
          page_size: 100,
          total_items: items.length,
          total_pages: 1,
        };
      }
      return {
        items: fixture.suppliers,
        page: 1,
        page_size: 200,
        total_items: fixture.suppliers.length,
        total_pages: 1,
      };
    }),
  };
}

function createCatalogMock(revision: string, replaceCatalogSnapshot = jest.fn()) {
  return {
    getSyncMeta: jest.fn(async () => ({
      id: 1,
      catalog_revision: revision,
      last_synced_at: '2026-01-01T00:00:00Z',
      inventory_count: 1,
      supplier_count: 1,
      aisle_count: 1,
      last_sync_attempt_at: null,
      last_successful_sync_at: '2026-01-01T00:00:00Z',
      last_sync_status: 'SUCCESS',
      catalog_projection_version: 1,
    })),
    replaceCatalogSnapshot,
    recordSyncAttempt: jest.fn(async () => undefined),
    recordSyncResult: jest.fn(async () => undefined),
    countActiveInventories: jest.fn(async () => 1),
    countActiveSuppliers: jest.fn(async () => 1),
    countProfiles: jest.fn(async () => 2),
  } as unknown as LocalCatalogRepository;
}

describe('CatalogSyncService', () => {
  const logger = createLogger(() => undefined);
  const connectivity = {
    getState: () => 'online' as const,
  } as ConnectivityService;

  it('skips catalog replace but still syncs recognition when catalog revision unchanged', async () => {
    const fixture = buildRemoteFixture(['inv-1']);
    const replaceCatalogSnapshot = jest.fn();
    const recognitionSync = {
      syncInventory: jest.fn(async () => ({
        ok: true,
        syncedAt: '2026-01-03T00:00:00Z',
      })),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      createCatalogMock(fixture.revision, replaceCatalogSnapshot),
      connectivity,
      logger,
      recognitionSync,
    );

    const result = await sync.syncCatalog();

    expect(result.ok).toBe(true);
    expect(result.status).toBe('SUCCESS');
    expect(result.catalogSkippedSameRevision).toBe(true);
    expect(result.catalogChanged).toBe(false);
    expect(replaceCatalogSnapshot).not.toHaveBeenCalled();
    expect(recognitionSync.syncInventory).toHaveBeenCalledWith('inv-1');
  });

  it('heals a pre-fix same-revision projection once and preserves LOCAL_ONLY aisles', async () => {
    const fixture = buildRemoteFixture(['inv-1']);
    let projectionVersion = 0;
    const rows = new Map([
      [
        'aisle-inv-1',
        { id: 'aisle-inv-1', client_supplier_id: null, origin: 'REMOTE', sync_status: 'REMOTE_SYNCED', active: 1 },
      ],
      [
        'local-1',
        { id: 'local-1', client_supplier_id: 'sup-local', origin: 'LOCAL', sync_status: 'LOCAL_ONLY', active: 1 },
      ],
    ]);
    const replaceCatalogSnapshot = jest.fn(async (snapshot: typeof fixture) => {
      for (const aisle of snapshot.aisles) {
        const existing = rows.get(aisle.id);
        rows.set(aisle.id, {
          id: aisle.id,
          client_supplier_id: aisle.client_supplier_id ?? null,
          origin: 'REMOTE',
          sync_status: 'REMOTE_SYNCED',
          active: existing?.active ?? 1,
        });
      }
      projectionVersion = 1;
    });
    const catalog = {
      ...createCatalogMock(fixture.revision, replaceCatalogSnapshot),
      getSyncMeta: jest.fn(async () => ({
        id: 1,
        catalog_revision: fixture.revision,
        catalog_projection_version: projectionVersion,
        last_synced_at: '2026-01-01T00:00:00Z',
        inventory_count: 1,
        supplier_count: 1,
        aisle_count: 1,
        last_sync_attempt_at: null,
        last_successful_sync_at: '2026-01-01T00:00:00Z',
        last_sync_status: 'SUCCESS',
      })),
    } as unknown as LocalCatalogRepository;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      catalog,
      connectivity,
      logger,
      createNoOpRecognitionSync(),
    );

    const healed = await sync.syncCatalog();
    expect(healed.catalogChanged).toBe(true);
    expect(replaceCatalogSnapshot).toHaveBeenCalledTimes(1);
    expect(rows.get('aisle-inv-1')?.client_supplier_id).toBe('sup-b');
    expect(rows.get('local-1')).toMatchObject({
      active: 1,
      client_supplier_id: 'sup-local',
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    });

    const unchanged = await sync.syncCatalog();
    expect(unchanged.catalogSkippedSameRevision).toBe(true);
    expect(replaceCatalogSnapshot).toHaveBeenCalledTimes(1);
  });

  it('invokes recognition service even when bundle revision is unchanged (service no-op)', async () => {
    const fixture = buildRemoteFixture(['inv-1']);
    const recognitionSync = {
      syncInventory: jest.fn(async () => ({
        ok: true,
        syncedAt: '2026-01-01T00:00:00Z',
        skippedSameRevision: true,
      })),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      createCatalogMock(fixture.revision),
      connectivity,
      logger,
      recognitionSync,
    );

    const result = await sync.syncCatalog();

    expect(result.ok).toBe(true);
    expect(result.status).toBe('NO_CHANGES');
    expect(recognitionSync.syncInventory).toHaveBeenCalledTimes(1);
  });

  it('downloads profile-only recognition changes when catalog revision is unchanged', async () => {
    const fixture = buildRemoteFixture(['inv-1']);
    const recognitionSync = {
      syncInventory: jest
        .fn()
        .mockResolvedValueOnce({ ok: true, syncedAt: '2026-01-01T00:00:00Z', skippedSameRevision: true })
        .mockResolvedValueOnce({
          ok: true,
          syncedAt: '2026-01-03T00:00:00Z',
          skippedSameRevision: false,
        }),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      createCatalogMock(fixture.revision),
      connectivity,
      logger,
      recognitionSync,
    );

    await sync.syncCatalog();
    const second = await sync.syncCatalog();

    expect(second.catalogSkippedSameRevision).toBe(true);
    expect(recognitionSync.syncInventory).toHaveBeenCalledTimes(2);
    expect(second.ok).toBe(true);
    expect(second.status).toBe('SUCCESS');
  });

  it('reports partial failure when recognition sync fails for one inventory', async () => {
    const fixture = buildRemoteFixture(['inv-a', 'inv-b']);
    const replaceCatalogSnapshot = jest.fn();
    const recognitionSync = {
      syncInventory: jest.fn(async (inventoryId: string) => {
        if (inventoryId === 'inv-b') {
          return { ok: false, syncedAt: null, errorCode: 'SYNC_FAILED' };
        }
        return { ok: true, syncedAt: '2026-01-03T00:00:00Z' };
      }),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => null),
        replaceCatalogSnapshot,
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult: jest.fn(async () => undefined),
        countActiveInventories: jest.fn(async () => 0),
        countActiveSuppliers: jest.fn(async () => 0),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      recognitionSync,
    );

    const result = await sync.syncCatalog();

    expect(result.ok).toBe(false);
    expect(result.status).toBe('PARTIAL');
    expect(result.catalogChanged).toBe(true);
    expect(result.errorCode).toBe('RECOGNITION_PARTIAL_FAILURE');
    expect(result.recognitionSyncedCount).toBe(1);
    expect(result.recognitionFailures).toEqual([
      { inventoryId: 'inv-b', errorCode: 'SYNC_FAILED' },
    ]);
    expect(replaceCatalogSnapshot).toHaveBeenCalledTimes(1);
  });

  it('retries recognition on a later sync even when catalog revision is already current', async () => {
    const fixture = buildRemoteFixture(['inv-a', 'inv-b']);
    const replaceCatalogSnapshot = jest.fn();
    const recognitionSync = {
      syncInventory: jest
        .fn()
        .mockImplementationOnce(async (inventoryId: string) =>
          inventoryId === 'inv-b'
            ? { ok: false, syncedAt: null, errorCode: 'SYNC_FAILED' }
            : { ok: true, syncedAt: '2026-01-03T00:00:00Z' },
        )
        .mockImplementationOnce(async (inventoryId: string) =>
          inventoryId === 'inv-b'
            ? { ok: false, syncedAt: null, errorCode: 'SYNC_FAILED' }
            : { ok: true, syncedAt: '2026-01-03T00:00:00Z' },
        )
        .mockImplementation(async () => ({
          ok: true,
          syncedAt: '2026-01-04T00:00:00Z',
        })),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => ({
          id: 1,
          catalog_revision: fixture.revision,
          last_synced_at: '2026-01-03T00:00:00Z',
          inventory_count: 2,
          supplier_count: 1,
          aisle_count: 2,
          last_sync_attempt_at: null,
          last_successful_sync_at: '2026-01-03T00:00:00Z',
          last_sync_status: 'PARTIAL',
          catalog_projection_version: 1,
        })),
        replaceCatalogSnapshot,
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult: jest.fn(async () => undefined),
        countActiveInventories: jest.fn(async () => 2),
        countActiveSuppliers: jest.fn(async () => 1),
        countProfiles: jest.fn(async () => 2),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      recognitionSync,
    );

    const first = await sync.syncCatalog();
    expect(first.ok).toBe(false);
    expect(first.status).toBe('PARTIAL');
    expect(replaceCatalogSnapshot).not.toHaveBeenCalled();

    const second = await sync.syncCatalog();
    expect(second.ok).toBe(true);
    expect(second.status).toBe('SUCCESS');
    expect(second.catalogSkippedSameRevision).toBe(true);
    expect(replaceCatalogSnapshot).not.toHaveBeenCalled();
    expect(recognitionSync.syncInventory).toHaveBeenCalledTimes(4);
  });

  it('returns offline error without calling API', async () => {
    const api = { get: jest.fn() };
    const catalog = {
      getSyncMeta: jest.fn(async () => null),
      countActiveInventories: jest.fn(async () => 0),
      countActiveSuppliers: jest.fn(async () => 0),
      countProfiles: jest.fn(async () => 0),
    } as unknown as LocalCatalogRepository;
    const offlineConnectivity = {
      getState: () => 'offline' as const,
    } as ConnectivityService;
    const sync = new CatalogSyncService(api as never, catalog, offlineConnectivity, logger, createNoOpRecognitionSync());
    const result = await sync.syncCatalog();
    expect(result.ok).toBe(false);
    expect(result.status).toBe('SKIPPED_OFFLINE');
    expect(result.errorCode).toBe('OFFLINE');
    expect(api.get).not.toHaveBeenCalled();
  });

  it('preserves previous catalog when replace fails', async () => {
    const replaceCatalogSnapshot = jest
      .fn()
      .mockRejectedValueOnce(new Error('suppliers failed'));
    const countActiveInventories = jest.fn(async () => 2);
    const fixture = buildRemoteFixture(['inv-new']);
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => null),
        replaceCatalogSnapshot,
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult: jest.fn(async () => undefined),
        countActiveInventories,
        countActiveSuppliers: jest.fn(async () => 1),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      createNoOpRecognitionSync(),
    );

    const failed = await sync.syncCatalog();
    expect(failed.ok).toBe(false);
    expect(failed.status).toBe('FAILED');
    expect(replaceCatalogSnapshot).toHaveBeenCalledTimes(1);
    expect(await countActiveInventories()).toBe(2);
  });

  it('persists new supplier when remote adds supplier C', async () => {
    const fixture = buildRemoteFixture(['inv-1'], [sampleSupplier('sup-c', 'Supplier C')]);
    const replaceCatalogSnapshot = jest.fn();
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => null),
        replaceCatalogSnapshot,
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult: jest.fn(async () => undefined),
        countActiveInventories: jest.fn(async () => 0),
        countActiveSuppliers: jest.fn(async () => 0),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      createNoOpRecognitionSync(),
    );

    const result = await sync.syncCatalog();
    expect(result.catalogChanged).toBe(true);
    expect(result.status).toBe('SUCCESS');
    expect(replaceCatalogSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({
        suppliers: expect.arrayContaining([expect.objectContaining({ id: 'sup-c' })]),
      }),
      expect.any(String),
    );
  });

  it('fetches all inventory pages', async () => {
    const inventoryIds = Array.from({ length: 150 }, (_, index) => `inv-${index + 1}`);
    const fixture = buildRemoteFixture(inventoryIds);
    const api = createApiMock(fixture, { pages: 2 });
    const replaceCatalogSnapshot = jest.fn();
    const sync = new CatalogSyncService(
      api as never,
      {
        getSyncMeta: jest.fn(async () => null),
        replaceCatalogSnapshot,
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult: jest.fn(async () => undefined),
        countActiveInventories: jest.fn(async () => 0),
        countActiveSuppliers: jest.fn(async () => 0),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      createNoOpRecognitionSync(),
    );

    const result = await sync.syncCatalog();
    expect(result.inventoryCount).toBe(150);
    const inventoryCalls = (api.get as jest.Mock).mock.calls.filter(
      (call: [string, ...unknown[]]) => call[0]?.startsWith('/api/v3/inventories/?'),
    );
    expect(inventoryCalls.length).toBe(2);
  });

  it('deduplicates concurrent sync requests via single-flight', async () => {
    const fixture = buildRemoteFixture(['inv-1']);
    let gate = 0;
    const api = {
      get: jest.fn(async (path: string) => {
        if (path.startsWith('/api/v3/inventories/?')) {
          gate += 1;
          if (gate === 1) {
            await new Promise((resolve) => setTimeout(resolve, 20));
          }
          return {
            items: fixture.inventories,
            page: 1,
            page_size: 100,
            total_items: 1,
            total_pages: 1,
          };
        }
        if (path.includes('/aisles')) {
          return {
            items: fixture.aisles,
            page: 1,
            page_size: 100,
            total_items: 1,
            total_pages: 1,
          };
        }
        return {
          items: fixture.suppliers,
          page: 1,
          page_size: 200,
          total_items: 1,
          total_pages: 1,
        };
      }),
    };
    const sync = new CatalogSyncService(
      api as never,
      createCatalogMock('old-revision'),
      connectivity,
      logger,
      createNoOpRecognitionSync(),
    );
    const first = sync.syncCatalog();
    const second = sync.syncCatalog();
    const [a, b] = await Promise.all([first, second]);
    expect(a).toBe(b);
    expect(api.get).toHaveBeenCalled();
  });
});

describe('CatalogSyncCoordinator', () => {
  const logger = createLogger(() => undefined);

  function buildCoordinator(lastSuccessfulSyncAt: string | null = null) {
    const fixture = buildRemoteFixture(['inv-1']);
    const syncService = new CatalogSyncService(
      createApiMock(fixture) as never,
      createCatalogMock(fixture.revision),
      { getState: () => 'online' as const } as ConnectivityService,
      logger,
      createNoOpRecognitionSync(),
    );
    const catalogRepo = {
      getSyncMeta: jest.fn(async () =>
        lastSuccessfulSyncAt
          ? {
              id: 1,
              catalog_revision: fixture.revision,
              last_synced_at: lastSuccessfulSyncAt,
              inventory_count: 1,
              supplier_count: 1,
              aisle_count: 1,
              last_sync_attempt_at: lastSuccessfulSyncAt,
              last_successful_sync_at: lastSuccessfulSyncAt,
              last_sync_status: 'SUCCESS',
            }
          : null,
      ),
    } as unknown as LocalCatalogRepository;
    const coordinator = new CatalogSyncCoordinator(
      syncService,
      { getState: () => 'online' as const } as ConnectivityService,
      catalogRepo,
    );
    return { coordinator, syncService, catalogRepo };
  }

  it('skips throttled auto-sync for foreground trigger', async () => {
    const recent = new Date().toISOString();
    const { coordinator } = buildCoordinator(recent);
    await coordinator.initialize();

    const result = await coordinator.requestSync('foreground');
    expect(result.status).toBe('SKIPPED_THROTTLE');
  });

  it('allows manual sync even when auto sync was recent', async () => {
    const recent = new Date().toISOString();
    const { coordinator } = buildCoordinator(recent);
    await coordinator.initialize();

    const result = await coordinator.syncManual();
    expect(result.status).not.toBe('SKIPPED_THROTTLE');
  });

  it('allows reconnect sync to bypass throttle', async () => {
    const recent = new Date().toISOString();
    const { coordinator } = buildCoordinator(recent);
    await coordinator.initialize();

    const result = await coordinator.requestSync('reconnect');
    expect(result.status).not.toBe('SKIPPED_THROTTLE');
  });

  it('shares single-flight across duplicate triggers', async () => {
    const fixture = buildRemoteFixture(['inv-1']);
    const api = {
      get: jest.fn(async (path: string) => {
        if (path.startsWith('/api/v3/inventories/?')) {
          await new Promise((resolve) => setTimeout(resolve, 20));
          return {
            items: fixture.inventories,
            page: 1,
            page_size: 100,
            total_items: 1,
            total_pages: 1,
          };
        }
        if (path.includes('/aisles')) {
          return {
            items: fixture.aisles,
            page: 1,
            page_size: 100,
            total_items: 1,
            total_pages: 1,
          };
        }
        return {
          items: fixture.suppliers,
          page: 1,
          page_size: 200,
          total_items: 1,
          total_pages: 1,
        };
      }),
    };
    const syncService = new CatalogSyncService(
      api as never,
      createCatalogMock(fixture.revision),
      { getState: () => 'online' as const } as ConnectivityService,
      logger,
      createNoOpRecognitionSync(),
    );
    const coordinator = new CatalogSyncCoordinator(
      syncService,
      { getState: () => 'online' as const } as ConnectivityService,
      { getSyncMeta: jest.fn(async () => null) } as unknown as LocalCatalogRepository,
    );
    const manual = coordinator.syncManual();
    const foreground = coordinator.requestSync('foreground', { force: true });
    const reconnect = coordinator.requestSync('reconnect');
    const results = await Promise.all([manual, foreground, reconnect]);
    expect(results[0]).toBe(results[1]);
    expect(results[1]).toBe(results[2]);
  });

  it('respects throttle interval constant', () => {
    expect(CATALOG_AUTO_SYNC_MIN_INTERVAL_MS).toBeGreaterThanOrEqual(30_000);
  });
});
