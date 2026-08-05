import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { CaptureSessionStatus } from '../../domain/enums/photoStatus';

/** Session statuses that may still produce a local ZIP handoff. */
export const EXPORTABLE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  'review',
  'local_completed',
];

export interface CanExportSessionInput {
  readonly session: CaptureSessionRow | null | undefined;
  readonly photos: readonly CapturePhotoRow[];
  /** Feature flag `mobileCsvExport` (default true when undefined). */
  readonly csvExportEnabled?: boolean;
  /** True while an export/share is already in flight for this UI. */
  readonly exportInProgress?: boolean;
}

export interface CanExportSessionResult {
  readonly ok: boolean;
  readonly reason: string | null;
}

/**
 * Centralized exportability gate for UI.
 * Does not duplicate ZIP readiness (CODE_SCAN / product rows) — that stays in LocalCsvExportService.
 * Ensures the session is present, not deleted, has freeze or stable photos, and export is not busy.
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
  if (!EXPORTABLE_SESSION_STATUSES.includes(session.status as CaptureSessionStatus)) {
    return {
      ok: false,
      reason: `La captura en estado "${session.status}" no se puede exportar desde aquí.`,
    };
  }
  const eligible = input.photos.filter((p) => p.status !== 'excluded' && p.status !== 'rejected');
  if (eligible.length === 0) {
    return { ok: false, reason: 'No hay fotos para exportar.' };
  }
  const hasFreeze = Boolean(session.active_freeze_id) || (session.capture_frozen_photo_count ?? 0) > 0;
  const hasStable = eligible.some((p) => p.status === 'stable');
  if (!hasFreeze && !hasStable) {
    return { ok: false, reason: 'La captura aún no tiene un freeze ni fotos estables para exportar.' };
  }
  return { ok: true, reason: null };
}

export function isSessionExportableStatus(status: string): boolean {
  return EXPORTABLE_SESSION_STATUSES.includes(status as CaptureSessionStatus);
}
