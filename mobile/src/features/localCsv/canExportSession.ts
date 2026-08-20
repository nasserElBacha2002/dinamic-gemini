import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { CaptureSessionStatus } from '../../domain/enums/photoStatus';

/**
 * Statuses where the UI historically highlighted export.
 * Export itself is allowed for any non-cancelled session with photos (see canExportSession).
 */
export const EXPORTABLE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  'preparing',
  'active',
  'paused',
  'finishing',
  'review',
  'local_completed',
  'uploading',
  'upload_review',
  'ready_to_process',
  'processing',
  'failed_processing',
  'failed',
  'completed',
];

export interface CanExportSessionInput {
  readonly session: CaptureSessionRow | null | undefined;
  readonly photos: readonly CapturePhotoRow[];
  /** Feature flag `mobileCsvExport` (default true when undefined). */
  readonly csvExportEnabled?: boolean;
  /**
   * True while an export/share is already in flight for this UI.
   * Does not grey out the ZIP control permanently — only prevents overlapping runs.
   */
  readonly exportInProgress?: boolean;
}

export interface CanExportSessionResult {
  readonly ok: boolean;
  readonly reason: string | null;
}

/**
 * Soft exportability check for ZIP handoff.
 * ZIP must stay available whenever there is a live session with photos —
 * do not require freeze, stable status, or a narrow session status.
 */
export function canExportSession(input: CanExportSessionInput): CanExportSessionResult {
  if (input.csvExportEnabled === false) {
    return { ok: false, reason: 'La exportación CSV local no está habilitada.' };
  }
  if (input.exportInProgress) {
    return { ok: false, reason: 'Exportación en curso.' };
  }
  const session = input.session;
  if (!session) {
    return { ok: false, reason: 'No se encontró la captura local.' };
  }
  if (session.status === 'cancelled') {
    return { ok: false, reason: 'La captura fue eliminada o cancelada.' };
  }
  const eligible = input.photos.filter((p) => p.status !== 'excluded' && p.status !== 'rejected');
  if (eligible.length === 0) {
    return { ok: false, reason: 'No hay fotos para exportar.' };
  }
  return { ok: true, reason: null };
}

export function isSessionExportableStatus(status: string): boolean {
  if (status === 'cancelled') return false;
  return EXPORTABLE_SESSION_STATUSES.includes(status as CaptureSessionStatus);
}
