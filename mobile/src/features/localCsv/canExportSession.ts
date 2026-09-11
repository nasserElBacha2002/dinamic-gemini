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

const IN_FLIGHT_DRAFT_STATUSES = new Set(['PENDING', 'SCANNING']);

export interface LocalScanDraftLike {
  readonly capture_photo_id: string;
  readonly status: string;
}

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
  /**
   * When local CODE_SCAN is enabled, pass drafts so ZIP stays blocked until
   * in-flight / missing scans settle (matches user-facing “escaneo terminado”).
   * Omit or pass `localCodeScanEnabled: false` to skip this gate.
   */
  readonly localCodeScanEnabled?: boolean;
  readonly localDetectionDrafts?: readonly LocalScanDraftLike[];
}

export interface CanExportSessionResult {
  readonly ok: boolean;
  readonly reason: string | null;
}

/**
 * Count eligible photos still waiting on local barcode CODE_SCAN.
 * In-flight drafts (PENDING/SCANNING) and stable photos without any draft count.
 */
export function countIncompleteLocalCodeScans(input: {
  readonly photos: readonly CapturePhotoRow[];
  readonly drafts: readonly LocalScanDraftLike[];
}): number {
  const eligible = input.photos.filter(
    (p) => p.status !== 'excluded' && p.status !== 'rejected' && p.status !== 'undecodable',
  );
  if (eligible.length === 0) {
    return 0;
  }
  const byPhoto = new Map<string, LocalScanDraftLike>();
  for (const draft of input.drafts) {
    const prev = byPhoto.get(draft.capture_photo_id);
    if (!prev) {
      byPhoto.set(draft.capture_photo_id, draft);
      continue;
    }
    // Prefer a real / in-flight scan over a capture-time NOT_APPLICABLE placeholder.
    if (prev.status === 'NOT_APPLICABLE' && draft.status !== 'NOT_APPLICABLE') {
      byPhoto.set(draft.capture_photo_id, draft);
    }
  }
  let incomplete = 0;
  for (const photo of eligible) {
    if (photo.status !== 'stable') {
      continue;
    }
    const draft = byPhoto.get(photo.id);
    if (!draft || draft.status === 'NOT_APPLICABLE') {
      incomplete += 1;
      continue;
    }
    if (IN_FLIGHT_DRAFT_STATUSES.has(draft.status)) {
      incomplete += 1;
    }
  }
  return incomplete;
}

/**
 * Soft exportability check for ZIP handoff.
 * ZIP must stay available whenever there is a live session with photos —
 * do not require freeze, stable status, or a narrow session status.
 * When local CODE_SCAN is on, also wait until drafts are no longer in flight.
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
  if (input.localCodeScanEnabled === true) {
    const incomplete = countIncompleteLocalCodeScans({
      photos: input.photos,
      drafts: input.localDetectionDrafts ?? [],
    });
    if (incomplete > 0) {
      return {
        ok: false,
        reason: `Escaneo local en curso (${incomplete}). Esperá a que termine antes de exportar.`,
      };
    }
  }
  return { ok: true, reason: null };
}

export function isSessionExportableStatus(status: string): boolean {
  if (status === 'cancelled') return false;
  return EXPORTABLE_SESSION_STATUSES.includes(status as CaptureSessionStatus);
}
