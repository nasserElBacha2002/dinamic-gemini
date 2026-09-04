import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';
import type { LocalLabelProfileResolver } from './localLabelProfileResolver';

export type OfflineReadinessStatus =
  | 'AVAILABLE'
  | 'MISSING_BUNDLE'
  | 'MISSING_SUPPLIER_PROFILE'
  | 'STALE'
  | 'INCOMPATIBLE';

export interface OfflineRecognitionReadiness {
  readonly status: OfflineReadinessStatus;
  readonly messageKey: string;
  readonly syncedAt: string | null;
  readonly missingKinds: readonly ('ITEM' | 'POSITION')[];
  readonly clientSupplierId: string | null;
  readonly staleDays: number | null;
}

const DEFAULT_STALE_DAYS = 14;

export async function checkOfflineRecognitionReadiness(input: {
  inventoryId: string;
  aisleId: string;
  repo: OfflineRecognitionConfigRepository;
  resolver: LocalLabelProfileResolver;
  nowMs?: () => number;
  staleAfterDays?: number;
}): Promise<OfflineRecognitionReadiness> {
  const meta = await input.repo.getSyncMeta(input.inventoryId);
  if (!meta) {
    return {
      status: 'MISSING_BUNDLE',
      messageKey: 'offline_recognition.missing_bundle',
      syncedAt: null,
      missingKinds: ['ITEM', 'POSITION'],
      clientSupplierId: null,
      staleDays: null,
    };
  }
  if (meta.bundle_schema_version !== 1) {
    return {
      status: 'INCOMPATIBLE',
      messageKey: 'offline_recognition.incompatible_bundle',
      syncedAt: meta.synced_at,
      missingKinds: [],
      clientSupplierId: null,
      staleDays: null,
    };
  }

  const resolved = await input.resolver.resolveForAisle(input.inventoryId, input.aisleId);
  const missing: ('ITEM' | 'POSITION')[] = [];
  if (resolved.item.missingSupplierProfile) missing.push('ITEM');
  if (resolved.position.missingSupplierProfile) missing.push('POSITION');
  if (missing.length) {
    return {
      status: 'MISSING_SUPPLIER_PROFILE',
      messageKey: 'offline_recognition.missing_supplier_profile',
      syncedAt: meta.synced_at,
      missingKinds: missing,
      clientSupplierId: resolved.item.clientSupplierId ?? resolved.position.clientSupplierId,
      staleDays: null,
    };
  }

  const now = (input.nowMs ?? Date.now)();
  const syncedMs = Date.parse(meta.synced_at);
  const staleDays =
    Number.isFinite(syncedMs) ? Math.floor((now - syncedMs) / (24 * 3600 * 1000)) : null;
  const threshold = input.staleAfterDays ?? DEFAULT_STALE_DAYS;
  if (staleDays != null && staleDays >= threshold) {
    return {
      status: 'STALE',
      messageKey: 'offline_recognition.stale_config',
      syncedAt: meta.synced_at,
      missingKinds: [],
      clientSupplierId: resolved.item.clientSupplierId,
      staleDays,
    };
  }

  return {
    status: 'AVAILABLE',
    messageKey: 'offline_recognition.available',
    syncedAt: meta.synced_at,
    missingKinds: [],
    clientSupplierId: resolved.item.clientSupplierId,
    staleDays,
  };
}
