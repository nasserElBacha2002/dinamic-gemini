import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';
import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';

export type InventoryCatalogReadiness = 'READY_OFFLINE' | 'PARTIAL' | 'NOT_READY';

export interface InventoryReadinessReport {
  readonly status: InventoryCatalogReadiness;
  readonly hasInventory: boolean;
  readonly supplierCount: number;
  readonly aisleCount: number;
  readonly hasRecognitionBundle: boolean;
}

export async function assessInventoryCatalogReadiness(input: {
  inventoryId: string;
  catalog: LocalCatalogRepository;
  recognitionRepo: OfflineRecognitionConfigRepository;
}): Promise<InventoryReadinessReport> {
  const inventory = await input.catalog.getInventoryById(input.inventoryId);
  if (!inventory || inventory.active !== 1) {
    return {
      status: 'NOT_READY',
      hasInventory: false,
      supplierCount: 0,
      aisleCount: 0,
      hasRecognitionBundle: false,
    };
  }
  const clientId = inventory.client_id;
  const supplierCount = clientId
    ? (await input.catalog.listSuppliers({ clientId, activeOnly: true })).total_items
    : 0;
  const aisleCount = (
    await input.catalog.listAisles({ inventoryId: input.inventoryId, activeOnly: true })
  ).total_items;
  const recognitionMeta = await input.recognitionRepo.getSyncMeta(input.inventoryId);
  const hasRecognitionBundle = Boolean(recognitionMeta);

  if (supplierCount > 0 && aisleCount > 0 && hasRecognitionBundle) {
    return {
      status: 'READY_OFFLINE',
      hasInventory: true,
      supplierCount,
      aisleCount,
      hasRecognitionBundle,
    };
  }

  if (hasInventoryMetadata(inventory)) {
    return {
      status: 'PARTIAL',
      hasInventory: true,
      supplierCount,
      aisleCount,
      hasRecognitionBundle,
    };
  }

  return {
    status: 'NOT_READY',
    hasInventory: true,
    supplierCount,
    aisleCount,
    hasRecognitionBundle,
  };
}

function hasInventoryMetadata(inventory: { name: string; status: string }): boolean {
  return Boolean(inventory.name?.trim() && inventory.status?.trim());
}
