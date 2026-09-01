import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';

export type SupplierOfflineReadinessStatus = 'READY_OFFLINE' | 'PARTIAL' | 'NOT_READY';

export interface SupplierOfflineReadiness {
  readonly status: SupplierOfflineReadinessStatus;
  readonly missingKinds: readonly ('ITEM' | 'POSITION')[];
  readonly message: string | null;
}

export async function canUseSupplierOffline(input: {
  readonly inventoryId: string;
  readonly inventoryClientId: string;
  readonly clientSupplierId: string;
  readonly catalog: LocalCatalogRepository;
  readonly recognitionRepo: OfflineRecognitionConfigRepository;
}): Promise<SupplierOfflineReadiness> {
  const supplier = await input.catalog.getSupplierById(input.inventoryClientId, input.clientSupplierId);
  if (!supplier) {
    return {
      status: 'NOT_READY',
      missingKinds: ['ITEM', 'POSITION'],
      message: 'El proveedor no está disponible offline.',
    };
  }
  if (supplier.active !== 1) {
    return {
      status: 'NOT_READY',
      missingKinds: [],
      message: 'El proveedor está inactivo.',
    };
  }
  if (supplier.client_id !== input.inventoryClientId) {
    return {
      status: 'NOT_READY',
      missingKinds: [],
      message: 'El proveedor no pertenece al cliente de este inventario.',
    };
  }

  const meta = await input.recognitionRepo.getSyncMeta(input.inventoryId);
  if (!meta) {
    return {
      status: 'NOT_READY',
      missingKinds: ['ITEM', 'POSITION'],
      message: 'No hay configuración de reconocimiento offline para este inventario.',
    };
  }

  const baseSources = await input.recognitionRepo.getSupplierBaseSources(
    input.inventoryId,
    input.clientSupplierId,
  );
  if (!baseSources) {
    return {
      status: 'NOT_READY',
      missingKinds: ['ITEM', 'POSITION'],
      message: 'Proveedor no está listo para trabajar offline.',
    };
  }

  const missing: ('ITEM' | 'POSITION')[] = [];
  if (baseSources.item_source === 'SUPPLIER') {
    const profile = await input.recognitionRepo.getProfile(
      input.inventoryId,
      input.clientSupplierId,
      'ITEM',
    );
    if (!profile) missing.push('ITEM');
  }
  if (baseSources.position_source === 'SUPPLIER') {
    const profile = await input.recognitionRepo.getProfile(
      input.inventoryId,
      input.clientSupplierId,
      'POSITION',
    );
    if (!profile) missing.push('POSITION');
  }

  if (missing.length > 0) {
    return {
      status: 'NOT_READY',
      missingKinds: missing,
      message: 'Proveedor no está listo para trabajar offline.',
    };
  }

  return { status: 'READY_OFFLINE', missingKinds: [], message: null };
}
