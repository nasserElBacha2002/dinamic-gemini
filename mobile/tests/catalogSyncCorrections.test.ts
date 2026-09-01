import { createLogger } from '../src/core/logging';
import { computeCatalogRevision } from '../src/features/catalog/catalogRevision';
import { CatalogSyncCoordinator } from '../src/features/catalog/catalogSyncCoordinator';
import {
  shouldTriggerReconnectCatalogSync,
  CATALOG_AUTO_SYNC_MIN_INTERVAL_MS,
} from '../src/features/catalog/catalogSyncPolicy';
import type { LocalCatalogRepository } from '../src/database/repositories/localCatalogRepository';
import { CatalogSyncService } from '../src/features/catalog/catalogSyncService';
import type { OfflineRecognitionSyncService } from '../src/features/offlineRecognition/offlineRecognitionSyncService';
import type { ConnectivityService } from '../src/services/connectivity/connectivity';

function createNoOpRecognitionSync(
  syncInventory: OfflineRecognitionSyncService['syncInventory'] = jest.fn(async () => ({
    ok: true,
    syncedAt: '2026-01-01T00:00:00Z',
    skippedSameRevision: true,
  })),
): OfflineRecognitionSyncService {
  return {
    syncInventory,
    fetchBundle: jest.fn(),
  } as unknown as OfflineRecognitionSyncService;
}

function sampleInventory(id: string) {
  return {
    id,
    name: `Inventory ${id}`,
    status: 'active',
    client_id: 'client-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    aisles_count: 1,
    pending_review_count: 0,
    last_activity_at: '2026-01-02T00:00:00Z',
    processing_mode: 'production',
  };
}

function buildRemoteFixture(inventoryIds: string[]) {
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
    client_supplier_id: null as string | null,
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
      client_supplier_id: aisle.client_supplier_id ?? null,
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

function createApiMock(fixture: ReturnType<typeof buildRemoteFixture>) {
  return {
    get: jest.fn(async (path: string) => {
      if (path.startsWith('/api/v3/inventories/?')) {
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
        return { items, page: 1, page_size: 100, total_items: items.length, total_pages: 1 };
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

describe('catalog sync final hardening', () => {
  const logger = createLogger(() => undefined);
  const connectivity = { getState: () => 'online' as const } as ConnectivityService;

  it('PARTIAL preserves previous successful timestamp', async () => {
    const fixture = buildRemoteFixture(['inv-a', 'inv-b']);
    const recordSyncResult = jest.fn(async () => undefined);
    const recognitionSync = {
      syncInventory: jest.fn(async (inventoryId: string) =>
        inventoryId === 'inv-b'
          ? { ok: false, syncedAt: null, errorCode: 'SYNC_FAILED' }
          : { ok: true, syncedAt: '2026-01-03T00:00:00Z' },
      ),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => ({
          id: 1,
          catalog_revision: null,
          last_synced_at: '2026-01-01T09:00:00Z',
          inventory_count: 0,
          supplier_count: 0,
          aisle_count: 0,
          last_sync_attempt_at: null,
          last_successful_sync_at: '2026-01-01T09:00:00Z',
          last_sync_status: 'SUCCESS',
        })),
        replaceCatalogSnapshot: jest.fn(),
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult,
        countActiveInventories: jest.fn(async () => 0),
        countActiveSuppliers: jest.fn(async () => 0),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      recognitionSync,
    );

    const result = await sync.syncCatalog();

    expect(result.status).toBe('PARTIAL');
    expect(result.syncedAt).toBeNull();
    expect(recordSyncResult).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'PARTIAL',
        successfulAtIso: null,
      }),
    );
  });

  it('SUCCESS and NO_CHANGES use current completion timestamp for profile-only updates', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-01-01T12:00:00Z'));

    const fixture = buildRemoteFixture(['inv-1']);
    const recordSyncResult = jest.fn(async () => undefined);
    const recognitionSync = {
      syncInventory: jest.fn(async () => ({
        ok: true,
        syncedAt: '2026-01-01T12:00:00Z',
        skippedSameRevision: false,
      })),
    } as unknown as OfflineRecognitionSyncService;
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => ({
          id: 1,
          catalog_revision: fixture.revision,
          last_synced_at: '2026-01-01T09:00:00Z',
          inventory_count: 1,
          supplier_count: 1,
          aisle_count: 1,
          last_sync_attempt_at: '2026-01-01T09:00:00Z',
          last_successful_sync_at: '2026-01-01T09:00:00Z',
          last_sync_status: 'SUCCESS',
        })),
        replaceCatalogSnapshot: jest.fn(),
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult,
        countActiveInventories: jest.fn(async () => 1),
        countActiveSuppliers: jest.fn(async () => 1),
        countProfiles: jest.fn(async () => 1),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      recognitionSync,
    );

    const result = await sync.syncCatalog();

    expect(result.status).toBe('SUCCESS');
    expect(result.syncedAt).toBe('2026-01-01T12:00:00.000Z');
    expect(recordSyncResult).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'SUCCESS',
        successfulAtIso: '2026-01-01T12:00:00.000Z',
      }),
    );

    jest.useRealTimers();
  });

  it('PARTIAL does not advance coordinator throttle timestamp', async () => {
    const fixture = buildRemoteFixture(['inv-a', 'inv-b']);
    const recordSyncResult = jest.fn(async () => undefined);
    const recognitionSync = {
      syncInventory: jest.fn(async (inventoryId: string) =>
        inventoryId === 'inv-b'
          ? { ok: false, syncedAt: null, errorCode: 'SYNC_FAILED' }
          : { ok: true, syncedAt: '2026-01-03T00:00:00Z' },
      ),
    } as unknown as OfflineRecognitionSyncService;
    const syncService = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => null),
        replaceCatalogSnapshot: jest.fn(),
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult,
        countActiveInventories: jest.fn(async () => 0),
        countActiveSuppliers: jest.fn(async () => 0),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      recognitionSync,
    );
    const coordinator = new CatalogSyncCoordinator(
      syncService,
      connectivity,
      {
        getSyncMeta: jest.fn(async () => ({
          id: 1,
          catalog_revision: fixture.revision,
          last_synced_at: '2026-01-01T09:00:00Z',
          inventory_count: 2,
          supplier_count: 1,
          aisle_count: 2,
          last_sync_attempt_at: '2026-01-01T09:00:00Z',
          last_successful_sync_at: '2026-01-01T09:00:00Z',
          last_sync_status: 'SUCCESS',
        })),
      } as unknown as LocalCatalogRepository,
    );
    await coordinator.initialize();

    await coordinator.requestSync('reconnect');
    const throttled = await coordinator.requestSync('foreground');

    expect(throttled.status).not.toBe('SKIPPED_THROTTLE');
  });

  it('profile-only SUCCESS throttles immediate foreground sync', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-01-01T12:00:00Z'));

    const fixture = buildRemoteFixture(['inv-1']);
    const recognitionSync = {
      syncInventory: jest.fn(async () => ({
        ok: true,
        syncedAt: '2026-01-01T12:00:00Z',
        skippedSameRevision: false,
      })),
    } as unknown as OfflineRecognitionSyncService;
    const syncService = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => ({
          id: 1,
          catalog_revision: fixture.revision,
          last_synced_at: '2026-01-01T09:00:00Z',
          inventory_count: 1,
          supplier_count: 1,
          aisle_count: 1,
          last_sync_attempt_at: '2026-01-01T09:00:00Z',
          last_successful_sync_at: '2026-01-01T09:00:00Z',
          last_sync_status: 'SUCCESS',
        })),
        replaceCatalogSnapshot: jest.fn(),
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult: jest.fn(async () => undefined),
        countActiveInventories: jest.fn(async () => 1),
        countActiveSuppliers: jest.fn(async () => 1),
        countProfiles: jest.fn(async () => 1),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      recognitionSync,
    );
    const coordinator = new CatalogSyncCoordinator(
      syncService,
      connectivity,
      {
        getSyncMeta: jest.fn(async () => ({
          id: 1,
          catalog_revision: fixture.revision,
          last_synced_at: '2026-01-01T09:00:00Z',
          inventory_count: 1,
          supplier_count: 1,
          aisle_count: 1,
          last_sync_attempt_at: '2026-01-01T09:00:00Z',
          last_successful_sync_at: '2026-01-01T09:00:00Z',
          last_sync_status: 'SUCCESS',
        })),
      } as unknown as LocalCatalogRepository,
    );
    await coordinator.initialize();

    const success = await coordinator.requestSync('reconnect');
    expect(success.status).toBe('SUCCESS');

    const throttled = await coordinator.requestSync('foreground');
    expect(throttled.status).toBe('SKIPPED_THROTTLE');
    expect(CATALOG_AUTO_SYNC_MIN_INTERVAL_MS).toBe(60_000);

    jest.useRealTimers();
  });

  it('FAILED preserves previous successful timestamp', async () => {
    const replaceCatalogSnapshot = jest.fn().mockRejectedValueOnce(new Error('db failed'));
    const recordSyncResult = jest.fn(async () => undefined);
    const fixture = buildRemoteFixture(['inv-1']);
    const sync = new CatalogSyncService(
      createApiMock(fixture) as never,
      {
        getSyncMeta: jest.fn(async () => null),
        replaceCatalogSnapshot,
        recordSyncAttempt: jest.fn(async () => undefined),
        recordSyncResult,
        countActiveInventories: jest.fn(async () => 1),
        countActiveSuppliers: jest.fn(async () => 1),
        countProfiles: jest.fn(async () => 0),
      } as unknown as LocalCatalogRepository,
      connectivity,
      logger,
      createNoOpRecognitionSync(),
    );

    const result = await sync.syncCatalog();

    expect(result.status).toBe('FAILED');
    expect(recordSyncResult).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'FAILED', successfulAtIso: null }),
    );
  });
});

describe('auth-gated reconnect policy', () => {
  it('logged out + reconnect does not trigger sync', () => {
    expect(shouldTriggerReconnectCatalogSync(false, 'offline', 'online')).toBe(false);
  });

  it('authenticated + reconnect triggers sync', () => {
    expect(shouldTriggerReconnectCatalogSync(true, 'offline', 'online')).toBe(true);
  });

  it('logout prevents reconnect sync until login', () => {
    expect(shouldTriggerReconnectCatalogSync(false, 'offline', 'online')).toBe(false);
    expect(shouldTriggerReconnectCatalogSync(true, 'offline', 'online')).toBe(true);
  });

  it('online to online does not trigger reconnect sync', () => {
    expect(shouldTriggerReconnectCatalogSync(true, 'online', 'online')).toBe(false);
  });

  it('foreground without auth is handled at App layer (auth required for foreground effect)', () => {
    expect(shouldTriggerReconnectCatalogSync(false, 'offline', 'online')).toBe(false);
  });
});
