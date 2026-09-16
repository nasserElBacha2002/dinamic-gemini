import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { CaptureRepository } from '../../database/repositories/captureRepository';

/**
 * Canonical photo set for ZIP export prep / export packaging.
 * Freeze wins when present; excluded/rejected never eligible; only `stable` is processable.
 */
export async function listCanonicalExportPhotos(
  captureRepo: CaptureRepository,
  sessionId: string,
  session?: CaptureSessionRow | null,
): Promise<{
  readonly session: CaptureSessionRow | null;
  readonly photos: CapturePhotoRow[];
  readonly usedFreeze: boolean;
}> {
  const resolved = session ?? (await captureRepo.getSession(sessionId));
  if (!resolved) {
    return { session: null, photos: [], usedFreeze: false };
  }
  if (resolved.active_freeze_id) {
    const frozen = await captureRepo.listFreezePhotos(resolved.active_freeze_id);
    return { session: resolved, photos: frozen, usedFreeze: true };
  }
  const photos = await captureRepo.listPhotos(sessionId);
  return { session: resolved, photos, usedFreeze: false };
}

/** Photos that must have a durable prep job when the export-prep flag is on. */
export function selectEligibleExportPrepPhotos(
  photos: readonly CapturePhotoRow[],
): CapturePhotoRow[] {
  return photos.filter((p) => p.status === 'stable');
}

/** Capture-side excluded/rejected (should not be processable; may need job EXCLUDED sync). */
export function selectNonProcessableExportPhotos(
  photos: readonly CapturePhotoRow[],
): CapturePhotoRow[] {
  return photos.filter((p) => p.status === 'excluded' || p.status === 'rejected');
}

/** Packaging eligibility (stable + any non-excluded/rejected used by legacy export). */
export function selectExportPackagingPhotos(
  photos: readonly CapturePhotoRow[],
): CapturePhotoRow[] {
  return photos.filter((p) => p.status !== 'excluded' && p.status !== 'rejected');
}
