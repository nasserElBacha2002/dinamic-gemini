/**
 * Helpers for the Procesar pasillo hub dialog: local results, excluded photos, aisle result rows.
 */

import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type {
  ConfirmedLocalResultRow,
  ConfirmedLocalResultSyncStatus,
} from '../../database/repositories/confirmedLocalResultRepository';

export type AisleResultOrigin = 'local' | 'server';

export type AisleResultUiStatus =
  | 'pending'
  | 'local_only'
  | 'uploading'
  | 'synced'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'conflict'
  | 'rejected';

export interface AisleResultListItem {
  readonly id: string;
  readonly origin: AisleResultOrigin;
  readonly title: string;
  readonly subtitle: string;
  readonly uiStatus: AisleResultUiStatus;
  readonly uiStatusLabel: string;
  readonly photoCount: number | null;
  readonly itemCount: number | null;
  readonly jobId: string | null;
  readonly localResultId: string | null;
  readonly canUpload: boolean;
  readonly canRetry: boolean;
  readonly canViewDetail: boolean;
  readonly errorCode: string | null;
  readonly createdAt: string;
}

const PENDING_SYNC: ReadonlySet<ConfirmedLocalResultSyncStatus> = new Set([
  'PENDING',
  'SYNCING',
  'RETRY_SCHEDULED',
]);

const FAILED_SYNC: ReadonlySet<ConfirmedLocalResultSyncStatus> = new Set([
  'FAILED_TERMINAL',
  'CONFLICT',
  'REJECTED',
]);

/** Sessions where restoring excluded capture photos is allowed without a new session. */
const RESTORE_ALLOWED_SESSION: ReadonlySet<string> = new Set([
  'preparing',
  'active',
  'paused',
  'finishing',
  'review',
  'uploading',
  'upload_review',
  'ready_to_process',
  'failed',
  'failed_processing',
]);

/** True when the capture sequence is locked (job already started / finished). */
export function isSessionSealedForPhotoRestore(session: CaptureSessionRow): boolean {
  if (session.backend_job_id) {
    return true;
  }
  return !RESTORE_ALLOWED_SESSION.has(session.status);
}

/**
 * Whether an excluded photo can be restored into the current session.
 * Queue exclusions that never reached the server stay restorable until a job starts.
 */
export function canRestoreExcludedPhoto(
  session: CaptureSessionRow,
  photo: CapturePhotoRow,
): boolean {
  if (
    photo.upload_status === 'remote_deleted' ||
    photo.upload_status === 'remote_delete_pending'
  ) {
    return false;
  }
  // Never uploaded — re-queue is safe even if local status drifted; block only after a job.
  if (photo.upload_status === 'excluded' && !photo.backend_asset_id) {
    if (session.backend_job_id) {
      return false;
    }
    return session.status !== 'completed' && session.status !== 'cancelled';
  }
  return !isSessionSealedForPhotoRestore(session);
}

export function isExcludedPhoto(photo: CapturePhotoRow): boolean {
  return (
    photo.status === 'excluded' ||
    photo.upload_status === 'excluded' ||
    photo.upload_status === 'remote_deleted' ||
    photo.upload_status === 'remote_delete_pending'
  );
}

export function countExcludedPhotos(photos: readonly CapturePhotoRow[]): number {
  return photos.filter(isExcludedPhoto).length;
}

export function countPendingLocalResults(rows: readonly ConfirmedLocalResultRow[]): number {
  return rows.filter((r) => PENDING_SYNC.has(r.sync_status) || FAILED_SYNC.has(r.sync_status)).length;
}

export function labelForLocalSyncStatus(status: ConfirmedLocalResultSyncStatus): string {
  switch (status) {
    case 'PENDING':
      return 'Solo local';
    case 'SYNCING':
      return 'Subiendo';
    case 'RETRY_SCHEDULED':
      return 'Reintento programado';
    case 'SYNCED':
      return 'Subido';
    case 'CONFLICT':
      return 'Conflicto';
    case 'REJECTED':
      return 'Rechazado';
    case 'FAILED_TERMINAL':
      return 'Fallido';
    default:
      return status;
  }
}

export function uiStatusForLocalSync(status: ConfirmedLocalResultSyncStatus): AisleResultUiStatus {
  switch (status) {
    case 'PENDING':
    case 'RETRY_SCHEDULED':
      return 'local_only';
    case 'SYNCING':
      return 'uploading';
    case 'SYNCED':
      return 'synced';
    case 'CONFLICT':
      return 'conflict';
    case 'REJECTED':
    case 'FAILED_TERMINAL':
      return 'failed';
    default:
      return 'pending';
  }
}

export function buildLocalResultListItems(
  rows: readonly ConfirmedLocalResultRow[],
): AisleResultListItem[] {
  const sorted = [...rows].sort((a, b) => {
    const byDate = b.confirmed_at.localeCompare(a.confirmed_at);
    if (byDate !== 0) return byDate;
    return b.id.localeCompare(a.id);
  });
  return sorted.map((row) => {
    const canUpload = PENDING_SYNC.has(row.sync_status) || row.sync_status === 'FAILED_TERMINAL';
    const canRetry = row.sync_status === 'RETRY_SCHEDULED' || row.sync_status === 'FAILED_TERMINAL';
    return {
      id: `local:${row.id}`,
      origin: 'local',
      title: `Resultado local · ${row.confirmed_internal_code}`,
      subtitle: `Confirmado ${formatShortDate(row.confirmed_at)} · ${labelForLocalSyncStatus(row.sync_status)}`,
      uiStatus: uiStatusForLocalSync(row.sync_status),
      uiStatusLabel: labelForLocalSyncStatus(row.sync_status),
      photoCount: 1,
      itemCount: 1,
      jobId: null,
      localResultId: row.id,
      canUpload,
      canRetry,
      canViewDetail: true,
      errorCode: row.sync_last_error_code,
      createdAt: row.confirmed_at,
    };
  });
}

export function buildServerJobListItem(input: {
  readonly jobId: string | null;
  readonly processingStatus: string;
  readonly updatedAt: string;
  readonly photoCount: number | null;
  readonly errorMessage: string | null;
}): AisleResultListItem | null {
  if (!input.jobId && input.processingStatus === 'idle') {
    return null;
  }
  const uiStatus = mapProcessingToUi(input.processingStatus);
  return {
    id: `server:${input.jobId ?? 'none'}`,
    origin: 'server',
    title: input.jobId ? `Trabajo servidor` : 'Procesamiento servidor',
    subtitle: input.jobId
      ? `Job ${input.jobId.slice(0, 8)}… · ${uiStatusLabel(uiStatus)}`
      : uiStatusLabel(uiStatus),
    uiStatus,
    uiStatusLabel: uiStatusLabel(uiStatus),
    photoCount: input.photoCount,
    itemCount: null,
    jobId: input.jobId,
    localResultId: null,
    canUpload: false,
    canRetry: uiStatus === 'failed',
    canViewDetail: Boolean(input.jobId),
    errorCode: input.errorMessage,
    createdAt: input.updatedAt,
  };
}

function mapProcessingToUi(status: string): AisleResultUiStatus {
  switch (status) {
    case 'processing':
    case 'queued':
    case 'running':
      return 'processing';
    case 'completed':
    case 'succeeded':
      return 'completed';
    case 'failed':
    case 'failed_processing':
    case 'cancelled':
      return 'failed';
    default:
      return 'pending';
  }
}

function uiStatusLabel(status: AisleResultUiStatus): string {
  switch (status) {
    case 'pending':
      return 'Pendiente';
    case 'local_only':
      return 'Solo local';
    case 'uploading':
      return 'Subiendo';
    case 'synced':
      return 'Subido';
    case 'processing':
      return 'Procesando en servidor';
    case 'completed':
      return 'Completado';
    case 'failed':
      return 'Fallido';
    case 'conflict':
      return 'Conflicto';
    case 'rejected':
      return 'Rechazado';
    default:
      return status;
  }
}

export function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('es-AR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/** Stable idempotency key for session-scoped local-result upload batch (retries reuse). */
export function buildLocalResultsUploadIdempotencyKey(input: {
  readonly clientId: string | null;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly sessionId: string;
}): string {
  const client = (input.clientId ?? 'unknown').trim() || 'unknown';
  return `mobile-local-results:${client}:${input.inventoryId}:${input.aisleId}:${input.sessionId}`;
}
