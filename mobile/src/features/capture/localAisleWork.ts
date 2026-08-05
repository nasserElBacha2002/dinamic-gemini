import type { CaptureSessionRow } from '../../database/schema/captureSchema';
import { isCaptureExclusiveSession } from '../../core/captureState';
import type { UploadSessionProgress } from '../upload/uploadQueue';

export type LocalAisleWorkKind =
  | 'capture_active'
  | 'capture_paused'
  | 'capture_review'
  | 'local_completed'
  | 'uploading'
  | 'ready_to_process'
  | 'processing'
  | 'failed_processing'
  | 'completed'
  | 'none';

export interface LocalAisleWork {
  readonly sessionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly inventoryName: string;
  readonly aisleName: string;
  readonly kind: LocalAisleWorkKind;
  readonly label: string;
  readonly pendingUploads: number;
  readonly updatedAt: string;
  readonly shortId: string;
  readonly frozenPhotoCount: number | null;
}

export function classifyLocalSession(
  session: CaptureSessionRow,
  upload?: UploadSessionProgress | null,
): LocalAisleWork {
  const pending = upload?.pending ?? 0;
  let kind: LocalAisleWorkKind = 'none';
  let label = '';
  if (session.status === 'active' || session.status === 'preparing' || session.status === 'finishing') {
    kind = 'capture_active';
    label = 'Captura en curso';
  } else if (session.status === 'paused') {
    kind = 'capture_paused';
    label = 'Captura pausada';
  } else if (session.status === 'review') {
    kind = 'capture_review';
    label = 'Fotos listas para revisar';
  } else if (session.status === 'local_completed') {
    kind = 'local_completed';
    label =
      pending > 0
        ? `Guardada localmente · ${pending} fotos pendientes de carga`
        : 'Guardada localmente · exportable offline';
  } else if (session.status === 'uploading' || session.status === 'upload_review') {
    kind = 'uploading';
    label =
      pending > 0 ? `${pending} fotos pendientes de carga` : 'Carga en progreso';
  } else if (session.status === 'ready_to_process') {
    kind = 'ready_to_process';
    label = 'Listo para procesar';
  } else if (session.status === 'processing') {
    kind = 'processing';
    label = 'Procesamiento en curso';
  } else if (session.status === 'failed_processing' || session.status === 'failed') {
    kind = 'failed_processing';
    label = 'Procesamiento fallido';
  } else if (session.status === 'completed') {
    kind = 'completed';
    label = 'Procesamiento completado';
  }
  return {
    sessionId: session.id,
    inventoryId: session.inventory_id,
    aisleId: session.aisle_id,
    inventoryName: session.inventory_name,
    aisleName: session.aisle_name,
    kind,
    label,
    pendingUploads: pending,
    updatedAt: session.updated_at,
    shortId: session.id.slice(0, 8),
    frozenPhotoCount: session.capture_frozen_photo_count,
  };
}

export function findExclusiveCapture(sessions: readonly CaptureSessionRow[]): CaptureSessionRow | null {
  return sessions.find((s) => isCaptureExclusiveSession(s.status as never)) ?? null;
}

/**
 * Sessions for one aisle, newest first (activity list is already updated_at DESC).
 */
export function listSessionsForAisle(
  sessions: readonly CaptureSessionRow[],
  aisleId: string,
): CaptureSessionRow[] {
  return sessions.filter((s) => s.aisle_id === aisleId);
}

/**
 * Primary work for an aisle card: prefer exclusive/open capture, else newest session.
 * Older sessions remain reachable via listSessionsForAisle / Actividad local.
 */
export function workForAisle(
  sessions: readonly CaptureSessionRow[],
  aisleId: string,
  uploads: readonly UploadSessionProgress[],
): LocalAisleWork | null {
  const forAisle = listSessionsForAisle(sessions, aisleId);
  if (forAisle.length === 0) {
    return null;
  }
  const exclusive = forAisle.find((s) => isCaptureExclusiveSession(s.status as never));
  const session = exclusive ?? forAisle[0]!;
  const upload = uploads.find((u) => u.sessionId === session.id) ?? null;
  return classifyLocalSession(session, upload);
}

export function classifySessionsForAisle(
  sessions: readonly CaptureSessionRow[],
  aisleId: string,
  uploads: readonly UploadSessionProgress[],
): LocalAisleWork[] {
  return listSessionsForAisle(sessions, aisleId)
    .map((s) =>
      classifyLocalSession(s, uploads.find((u) => u.sessionId === s.id) ?? null),
    )
    .filter((w) => w.kind !== 'none');
}
