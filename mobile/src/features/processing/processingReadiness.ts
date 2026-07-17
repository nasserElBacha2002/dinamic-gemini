import type { CapturePhotoRow } from '../../database/schema/captureSchema';

export interface ProcessingReadiness {
  readonly ready: boolean;
  readonly includedPhotos: number;
  readonly uploadedPhotos: number;
  readonly pendingPhotos: number;
  readonly failedPhotos: number;
  readonly reason: string | null;
}

export function computeProcessingReadiness(
  photos: readonly CapturePhotoRow[],
  uploadGate: 'ready' | 'pending' | 'blocked',
): ProcessingReadiness {
  const included = photos.filter((p) => p.status === 'stable');
  const uploaded = included.filter((p) => p.upload_status === 'uploaded' && p.backend_asset_id);
  const pending = included.filter((p) =>
    ['not_queued', 'queued', 'preparing', 'uploading', 'retryable_error', 'remote_delete_pending'].includes(
      p.upload_status,
    ),
  );
  const failed = included.filter((p) => p.upload_status === 'permanent_error');
  const validating = photos.some((p) => p.status === 'detected' || p.status === 'waiting_stability');

  if (validating) {
    return {
      ready: false,
      includedPhotos: included.length,
      uploadedPhotos: uploaded.length,
      pendingPhotos: pending.length,
      failedPhotos: failed.length,
      reason: 'Hay fotografías en validación.',
    };
  }
  if (uploadGate === 'pending') {
    return {
      ready: false,
      includedPhotos: included.length,
      uploadedPhotos: uploaded.length,
      pendingPhotos: pending.length,
      failedPhotos: failed.length,
      reason: 'Aún hay cargas pendientes.',
    };
  }
  if (uploadGate === 'blocked' || failed.length > 0) {
    return {
      ready: false,
      includedPhotos: included.length,
      uploadedPhotos: uploaded.length,
      pendingPhotos: pending.length,
      failedPhotos: failed.length,
      reason: 'Hay errores permanentes de carga por resolver.',
    };
  }
  if (uploaded.length === 0) {
    return {
      ready: false,
      includedPhotos: included.length,
      uploadedPhotos: 0,
      pendingPhotos: pending.length,
      failedPhotos: failed.length,
      reason: 'No hay fotografías cargadas para procesar.',
    };
  }
  return {
    ready: true,
    includedPhotos: included.length,
    uploadedPhotos: uploaded.length,
    pendingPhotos: pending.length,
    failedPhotos: failed.length,
    reason: null,
  };
}
