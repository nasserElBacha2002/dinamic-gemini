import type { CaptureContext, CaptureSnapshot } from '../features/capture/captureService';
import type { CapturePhotoRow } from '../database/schema/captureSchema';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function countPhotos(photos: CapturePhotoRow[]) {
  return {
    total: photos.length,
    waiting: photos.filter((p) => p.status === 'detected' || p.status === 'waiting_stability').length,
    stable: photos.filter((p) => p.status === 'stable').length,
    errors: photos.filter((p) => p.status === 'unstable' || p.status === 'undecodable').length,
    excluded: photos.filter((p) => p.status === 'excluded').length,
  };
}

export function captureContextFrom(
  snapshot: CaptureSnapshot | null,
  inventory: InventoryListItemDto | null,
  aisle: AisleDto | null,
): CaptureContext | null {
  if (snapshot?.context) return snapshot.context;
  if (!inventory || !aisle) return null;
  return {
    inventoryId: inventory.id,
    inventoryName: inventory.name,
    aisleId: aisle.id,
    aisleName: aisle.code,
  };
}
