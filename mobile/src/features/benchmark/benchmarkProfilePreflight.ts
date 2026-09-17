import {
  AUTHORIZED_BENCHMARK_CLIENT_ID,
  AUTHORIZED_BENCHMARK_PROFILE_NAME,
  AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
  BENCHMARK_RECOGNITION_HOST_INVENTORY_ID,
} from './authorizedIds';
import { canUseSupplierOffline } from '../aisles/canUseSupplierOffline';
import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';

export interface BenchmarkProfilePreflightResult {
  readonly ok: boolean;
  readonly failureCode: string | null;
  readonly failureDetail: string | null;
  readonly clientId: string;
  readonly supplierRouteId: string;
  readonly resolvedClientId: string | null;
  readonly resolvedSupplierId: string | null;
  readonly resolvedClientSupplierId: string | null;
  readonly resolvedProfileName: string | null;
  readonly itemProfileVersion: number | null;
  readonly positionProfileVersion: number | null;
  readonly configurationSource: string | null;
  readonly snapshotResolved: boolean;
  readonly hostInventoryId: string;
  readonly fallbackUsed: boolean;
}

/**
 * Read-only Andes preflight against local catalog + recognition SQLite.
 * Does not mutate ClientSupplier or profiles. Fails closed on DINAMIC fallback.
 */
export async function runBenchmarkProfilePreflight(input: {
  readonly catalog: LocalCatalogRepository;
  readonly recognitionRepo: OfflineRecognitionConfigRepository;
  readonly clientId?: string;
  readonly supplierRouteId?: string;
  readonly hostInventoryId?: string;
}): Promise<BenchmarkProfilePreflightResult> {
  const clientId = input.clientId ?? AUTHORIZED_BENCHMARK_CLIENT_ID;
  const supplierRouteId = input.supplierRouteId ?? AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID;
  const hostInventoryId = input.hostInventoryId ?? BENCHMARK_RECOGNITION_HOST_INVENTORY_ID;

  const fail = (code: string, detail: string): BenchmarkProfilePreflightResult => ({
    ok: false,
    failureCode: code,
    failureDetail: detail,
    clientId,
    supplierRouteId,
    resolvedClientId: null,
    resolvedSupplierId: null,
    resolvedClientSupplierId: null,
    resolvedProfileName: null,
    itemProfileVersion: null,
    positionProfileVersion: null,
    configurationSource: null,
    snapshotResolved: false,
    hostInventoryId,
    fallbackUsed: false,
  });

  if (clientId !== AUTHORIZED_BENCHMARK_CLIENT_ID) {
    return fail('UNAUTHORIZED_CLIENT', 'clientId does not match authorized Andes client');
  }
  if (supplierRouteId !== AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID) {
    return fail('UNAUTHORIZED_SUPPLIER', 'supplierRouteId does not match authorized Andes ClientSupplier');
  }

  const inventory = await input.catalog.getInventoryById(hostInventoryId);
  if (!inventory || inventory.active !== 1) {
    return fail('HOST_INVENTORY_MISSING', 'Recognition host inventory missing or inactive');
  }
  if (inventory.client_id !== clientId) {
    return fail('HOST_INVENTORY_CLIENT_MISMATCH', 'Host inventory client_id mismatch');
  }

  const supplier = await input.catalog.getSupplierById(clientId, supplierRouteId);
  if (!supplier) {
    return fail('CLIENT_SUPPLIER_MISSING', 'ClientSupplier not found for client');
  }
  if (supplier.client_id !== clientId) {
    return fail('CLIENT_SUPPLIER_CLIENT_MISMATCH', 'ClientSupplier.client_id mismatch');
  }
  if (supplier.active !== 1) {
    return fail('CLIENT_SUPPLIER_INACTIVE', 'ClientSupplier is inactive');
  }
  const profileName = (supplier.name ?? '').trim().toLowerCase();
  if (profileName !== AUTHORIZED_BENCHMARK_PROFILE_NAME) {
    return fail(
      'PROFILE_NAME_MISMATCH',
      `expected profile name "${AUTHORIZED_BENCHMARK_PROFILE_NAME}", got "${profileName || 'empty'}"`,
    );
  }

  const readiness = await canUseSupplierOffline({
    inventoryId: hostInventoryId,
    inventoryClientId: clientId,
    clientSupplierId: supplierRouteId,
    catalog: input.catalog,
    recognitionRepo: input.recognitionRepo,
  });
  if (readiness.status !== 'READY_OFFLINE') {
    return fail(
      'OFFLINE_NOT_READY',
      readiness.message ?? `missing=${readiness.missingKinds.join(',')}`,
    );
  }

  const baseSources = await input.recognitionRepo.getSupplierBaseSources(
    hostInventoryId,
    supplierRouteId,
  );
  if (!baseSources) {
    return fail('BASE_SOURCES_MISSING', 'No supplier base sources in recognition bundle');
  }
  if (baseSources.item_source !== 'SUPPLIER' || baseSources.position_source !== 'SUPPLIER') {
    return fail(
      'DINAMIC_FALLBACK_DETECTED',
      `item_source=${baseSources.item_source} position_source=${baseSources.position_source}`,
    );
  }

  const itemProfile = await input.recognitionRepo.getProfile(
    hostInventoryId,
    supplierRouteId,
    'ITEM',
  );
  const positionProfile = await input.recognitionRepo.getProfile(
    hostInventoryId,
    supplierRouteId,
    'POSITION',
  );
  if (!itemProfile) {
    return fail('ITEM_PROFILE_MISSING', 'ITEM recognition profile missing');
  }
  if (!positionProfile) {
    return fail('POSITION_PROFILE_MISSING', 'POSITION recognition profile missing');
  }
  if (itemProfile.source !== 'SUPPLIER' || positionProfile.source !== 'SUPPLIER') {
    return fail('PROFILE_SOURCE_NOT_SUPPLIER', 'Profile source is not SUPPLIER');
  }

  return {
    ok: true,
    failureCode: null,
    failureDetail: null,
    clientId,
    supplierRouteId,
    resolvedClientId: clientId,
    resolvedSupplierId: supplierRouteId,
    resolvedClientSupplierId: supplier.id,
    resolvedProfileName: profileName,
    itemProfileVersion: itemProfile.profile_version,
    positionProfileVersion: positionProfile.profile_version,
    configurationSource: 'offline_recognition_profiles:SUPPLIER',
    snapshotResolved: true,
    hostInventoryId,
    fallbackUsed: false,
  };
}
