import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import type { CapturePhotoRow } from '../../database/schema/captureSchema';
import { isDraftExportReady } from './supplierExportSemantics';

export type LocalCsvExportBlockCode =
  | 'PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED'
  | 'PACKAGE_EXPORT_SCAN_UNSUPPORTED'
  | 'PACKAGE_EXPORT_PHOTOS_UNSTABLE';

function snapshotMissingSupplierProfile(raw: string | null | undefined): boolean {
  if (!raw?.trim()) return false;
  try {
    const snap = JSON.parse(raw) as {
      item_profile_missing?: boolean;
      item?: { missing?: boolean };
    };
    return snap.item_profile_missing === true || snap.item?.missing === true;
  } catch {
    return false;
  }
}

/**
 * Detect a more specific export failure before generic LOCAL_PENDING messaging.
 */
export function diagnoseExportBlockers(
  photos: readonly CapturePhotoRow[],
  drafts: readonly LocalDetectionDraftRow[],
): { code: LocalCsvExportBlockCode; detail: string } | null {
  const draftByPhoto = new Map(drafts.map((d) => [d.capture_photo_id, d]));
  let pending = 0;
  let unstableOnly = 0;
  let offlineProfileMissing = false;
  let scanUnsupported = false;

  for (const photo of photos) {
    if (photo.status === 'excluded' || photo.status === 'rejected') {
      continue;
    }
    const draft = draftByPhoto.get(photo.id);
    if (isDraftExportReady(draft)) {
      continue;
    }
    pending += 1;
    if (photo.status !== 'stable') {
      unstableOnly += 1;
    }
    if (snapshotMissingSupplierProfile(draft?.recognition_profile_snapshot_json)) {
      offlineProfileMissing = true;
    }
    const errorCode = (draft?.error_code ?? '').trim().toUpperCase();
    if (
      errorCode === 'SDK_UNAVAILABLE' ||
      errorCode === 'UNSUPPORTED_ANDROID_VERSION' ||
      errorCode === 'DISABLED'
    ) {
      scanUnsupported = true;
    }
  }

  if (pending === 0) {
    return null;
  }
  if (offlineProfileMissing) {
    return {
      code: 'PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED',
      detail: `${pending} foto(s) sin perfil Supplier offline sincronizado`,
    };
  }
  if (scanUnsupported) {
    return {
      code: 'PACKAGE_EXPORT_SCAN_UNSUPPORTED',
      detail: 'escaneo local de códigos no disponible en este dispositivo',
    };
  }
  if (unstableOnly === pending) {
    return {
      code: 'PACKAGE_EXPORT_PHOTOS_UNSTABLE',
      detail: `${pending} foto(s) aún no estabilizadas`,
    };
  }
  return null;
}
