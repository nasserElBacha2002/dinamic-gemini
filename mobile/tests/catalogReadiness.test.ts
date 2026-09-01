import { assessInventoryCatalogReadiness } from '../src/features/catalog/catalogReadiness';
import type { LocalCatalogRepository } from '../src/database/repositories/localCatalogRepository';
import type { OfflineRecognitionConfigRepository } from '../src/database/repositories/offlineRecognitionConfigRepository';

describe('assessInventoryCatalogReadiness', () => {
  it('requires recognition bundle for READY_OFFLINE', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => ({
        id: 'inv-1',
        client_id: 'client-1',
        name: 'Inventory',
        status: 'active',
        active: 1,
      })),
      listSuppliers: jest.fn(async () => ({
        total_items: 2,
        items: [],
        page: 1,
        page_size: 200,
        total_pages: 1,
      })),
      listAisles: jest.fn(async () => ({
        total_items: 3,
        items: [],
        page: 1,
        page_size: 50,
        total_pages: 1,
      })),
    } as unknown as LocalCatalogRepository;
    const recognitionRepo = {
      getSyncMeta: jest.fn(async () => null),
    } as unknown as OfflineRecognitionConfigRepository;

    const report = await assessInventoryCatalogReadiness({
      inventoryId: 'inv-1',
      catalog,
      recognitionRepo,
    });

    expect(report.status).toBe('PARTIAL');
    expect(report.hasRecognitionBundle).toBe(false);
  });

  it('marks READY_OFFLINE only when catalog and recognition bundle exist', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => ({
        id: 'inv-1',
        client_id: 'client-1',
        name: 'Inventory',
        status: 'active',
        active: 1,
      })),
      listSuppliers: jest.fn(async () => ({
        total_items: 1,
        items: [],
        page: 1,
        page_size: 200,
        total_pages: 1,
      })),
      listAisles: jest.fn(async () => ({
        total_items: 1,
        items: [],
        page: 1,
        page_size: 50,
        total_pages: 1,
      })),
    } as unknown as LocalCatalogRepository;
    const recognitionRepo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'rev-1',
        synced_at: '2026-01-01T00:00:00Z',
        generated_at: null,
      })),
    } as unknown as OfflineRecognitionConfigRepository;

    const report = await assessInventoryCatalogReadiness({
      inventoryId: 'inv-1',
      catalog,
      recognitionRepo,
    });

    expect(report.status).toBe('READY_OFFLINE');
  });
});
