import type { CaptureSessionRow } from '../../database/schema/captureSchema';
import { isCaptureExclusiveSession } from '../../core/captureState';
import type { UploadSessionProgress } from '../upload/uploadQueue';

export type LocalAisleWorkKind =
  | 'capture_active'
  | 'capture_paused'
  | 'capture_review'
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
  };
}

export function findExclusiveCapture(sessions: readonly CaptureSessionRow[]): CaptureSessionRow | null {
  return sessions.find((s) => isCaptureExclusiveSession(s.status as never)) ?? null;
}

export function workForAisle(
  sessions: readonly CaptureSessionRow[],
  aisleId: string,
  uploads: readonly UploadSessionProgress[],
): LocalAisleWork | null {
  const session = sessions.find((s) => s.aisle_id === aisleId);
  if (!session) {
    return null;
  }
  const upload = uploads.find((u) => u.sessionId === session.id) ?? null;
  return classifyLocalSession(session, upload);
}
