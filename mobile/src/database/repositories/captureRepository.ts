import type { CompositeCursor } from '../../core/compositeCursor';
import { EMPTY_CURSOR } from '../../core/compositeCursor';
import { nextSequenceAssignments, sortByGalleryOrder } from '../../core/captureSequence';
import {
  CAPTURE_EXCLUSIVE_SESSION_STATUSES,
  OPEN_CAPTURE_SESSION_STATUSES,
  canTransitionPhoto,
  canTransitionSession,
} from '../../core/captureState';
import type { CaptureMarker } from '../../domain/entities/captureMarker';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus, CaptureSessionStatus } from '../../domain/enums/photoStatus';
import type { PhotoUploadStatus } from '../../domain/enums/uploadStatus';
import type { SQLiteDatabase } from '../database';
import {
  runExclusiveDbWriteWithBusyRetry,
  runImmediateTransaction,
  withSqliteBusyRetry,
} from '../sqliteWriteGate';
import type { CapturePhotoRow, CaptureSessionRow } from '../schema/captureSchema';

export interface CreateCaptureSessionInput {
  readonly id: string;
  readonly inventoryId: string;
  readonly inventoryName: string;
  readonly aisleId: string;
  readonly aisleName: string;
  readonly marker: CaptureMarker;
  readonly uploadBatchId: string;
}

export interface CreateCaptureSessionResult {
  readonly session: CaptureSessionRow;
  readonly created: boolean;
}

export interface StabilityResultInput {
  readonly sessionId: string;
  readonly assetId: string;
  readonly status: Extract<CapturePhotoStatus, 'stable' | 'unstable' | 'undecodable' | 'rejected'>;
  readonly error: string | null;
  readonly checks: number;
}

export class CaptureRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async createSession(input: CreateCaptureSessionInput): Promise<CaptureSessionRow> {
    const result = await this.createSessionExclusive(input);
    return result.session;
  }

  async createSessionExclusive(input: CreateCaptureSessionInput): Promise<CreateCaptureSessionResult> {
    return runImmediateTransaction(this.db, async () => {
      const existing = await this.findExclusiveCaptureSession();
      if (existing) {
        return { session: existing, created: false };
      }
      const session = await this.insertSession(input, 'preparing');
      return { session, created: true };
    });
  }

  private async insertSession(
    input: CreateCaptureSessionInput,
    status: CaptureSessionStatus,
  ): Promise<CaptureSessionRow> {
    const now = new Date().toISOString();
    const cursor = input.marker.assetId && input.marker.dateAdded !== null
      ? { dateAdded: input.marker.dateAdded, assetId: input.marker.assetId }
      : EMPTY_CURSOR;
    await this.db.runAsync(
      `INSERT INTO capture_sessions (
        id, inventory_id, inventory_name, aisle_id, aisle_name, status, started_at, finished_at,
        initial_asset_id, initial_date_added, initial_date_modified, initial_display_name,
        initial_size, initial_bucket_id, scan_cursor_date_added, scan_cursor_asset_id,
        last_valid_cursor_date_added, last_valid_cursor_asset_id,
        upload_batch_id, upload_status, processing_status,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'idle', 'idle', ?, ?);`,
      input.id,
      input.inventoryId,
      input.inventoryName,
      input.aisleId,
      input.aisleName,
      status,
      now,
      null,
      input.marker.assetId,
      input.marker.dateAdded,
      input.marker.dateModified,
      input.marker.displayName,
      input.marker.size,
      input.marker.bucketId,
      cursor.dateAdded,
      cursor.assetId,
      cursor.dateAdded,
      cursor.assetId,
      input.uploadBatchId,
      now,
      now,
    );
    const row = await this.getSession(input.id);
    if (!row) {
      throw new Error('Failed to create capture session');
    }
    return row;
  }

  async getSession(id: string): Promise<CaptureSessionRow | null> {
    return this.db.getFirstAsync<CaptureSessionRow>('SELECT * FROM capture_sessions WHERE id = ?;', id);
  }

  async listActivitySessions(): Promise<CaptureSessionRow[]> {
    const placeholders = OPEN_CAPTURE_SESSION_STATUSES.map(() => '?').join(', ');
    return this.db.getAllAsync<CaptureSessionRow>(
      `SELECT * FROM capture_sessions WHERE status IN (${placeholders}) ORDER BY updated_at DESC;`,
      ...OPEN_CAPTURE_SESSION_STATUSES,
    );
  }

  /** @deprecated Prefer listActivitySessions / findExclusiveCaptureSession. */
  async listOpenSessions(): Promise<CaptureSessionRow[]> {
    return this.listActivitySessions();
  }

  async listExclusiveCaptureSessions(): Promise<CaptureSessionRow[]> {
    const placeholders = CAPTURE_EXCLUSIVE_SESSION_STATUSES.map(() => '?').join(', ');
    return this.db.getAllAsync<CaptureSessionRow>(
      `SELECT * FROM capture_sessions WHERE status IN (${placeholders}) ORDER BY updated_at DESC;`,
      ...CAPTURE_EXCLUSIVE_SESSION_STATUSES,
    );
  }

  async findExclusiveCaptureSession(): Promise<CaptureSessionRow | null> {
    const [session] = await this.listExclusiveCaptureSessions();
    return session ?? null;
  }

  async findCurrentOpenSession(): Promise<CaptureSessionRow | null> {
    return this.findExclusiveCaptureSession();
  }

  async findOpenSessionForAisle(inventoryId: string, aisleId: string): Promise<CaptureSessionRow | null> {
    const placeholders = OPEN_CAPTURE_SESSION_STATUSES.map(() => '?').join(', ');
    return this.db.getFirstAsync<CaptureSessionRow>(
      `SELECT * FROM capture_sessions WHERE inventory_id = ? AND aisle_id = ? AND status IN (${placeholders}) ORDER BY updated_at DESC LIMIT 1;`,
      inventoryId,
      aisleId,
      ...OPEN_CAPTURE_SESSION_STATUSES,
    );
  }

  async updateSessionStatus(id: string, status: CaptureSessionStatus, finished = false): Promise<void> {
    // Serialize with capture finish / offline enqueue / local scan writers.
    await runExclusiveDbWriteWithBusyRetry(async () => {
      const current = await this.getSession(id);
      if (!current) {
        throw new Error(`Capture session not found: ${id}`);
      }
      if (!canTransitionSession(current.status, status)) {
        throw new Error(`Invalid capture session transition: ${current.status} -> ${status}`);
      }
      await this.db.runAsync(
        'UPDATE capture_sessions SET status = ?, finished_at = COALESCE(?, finished_at), updated_at = ? WHERE id = ?;',
        status,
        finished ? new Date().toISOString() : null,
        new Date().toISOString(),
        id,
      );
    });
  }

  async markProcessStartFailed(
    id: string,
    patch: {
      readonly errorCode: string;
      readonly message: string;
      readonly sessionStatus?: CaptureSessionStatus;
      readonly clearBackendJobId?: boolean;
    },
  ): Promise<void> {
    const now = new Date().toISOString();
    const sessionStatus = patch.sessionStatus ?? 'uploading';
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_sessions SET
        processing_status = 'failed',
        status = ?,
        processing_finished_at = ?,
        last_processing_error = ?,
        backend_job_id = CASE WHEN ? THEN NULL ELSE backend_job_id END,
        updated_at = ?
       WHERE id = ?;`,
        sessionStatus,
        now,
        `[${patch.errorCode}] ${patch.message}`.slice(0, 2000),
        patch.clearBackendJobId ? 1 : 0,
        now,
        id,
      ),
    );
  }

  async listSessionsStuckStarting(olderThanIso: string): Promise<CaptureSessionRow[]> {
    const rows = await this.db.getAllAsync<CaptureSessionRow>(
      `SELECT * FROM capture_sessions
       WHERE processing_status = 'starting'
         AND (backend_job_id IS NULL OR TRIM(backend_job_id) = '')
         AND (process_confirmed_at IS NULL OR TRIM(process_confirmed_at) = '')
         AND COALESCE(processing_started_at, created_at) < ?
       ORDER BY updated_at ASC
       LIMIT 50;`,
      olderThanIso,
    );
    return rows;
  }

  async persistProcessAttempt(
    sessionId: string,
    patch: {
      readonly processAttemptId: string;
      readonly processIdempotencyKey: string;
      readonly processRequestedAt: string;
    },
  ): Promise<void> {
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_sessions SET
          process_attempt_id = ?,
          process_idempotency_key = ?,
          process_requested_at = ?,
          updated_at = ?
         WHERE id = ?;`,
        patch.processAttemptId,
        patch.processIdempotencyKey,
        patch.processRequestedAt,
        now,
        sessionId,
      ),
    );
  }

  async confirmProcessAttempt(sessionId: string, backendJobId: string): Promise<void> {
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_sessions SET
          process_confirmed_at = ?,
          backend_job_id = ?,
          updated_at = ?
         WHERE id = ?;`,
        now,
        backendJobId,
        now,
        sessionId,
      ),
    );
  }

  async touchRecoveryCheck(sessionId: string): Promise<void> {
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_sessions SET last_recovery_check_at = ?, updated_at = ? WHERE id = ?;`,
        now,
        now,
        sessionId,
      ),
    );
  }

  async updateSessionUploadMeta(
    id: string,
    patch: {
      readonly uploadStatus?: string;
      readonly processingStatus?: string;
      readonly backendJobId?: string | null;
      readonly lastUploadError?: string | null;
      readonly lastProcessingError?: string | null;
      readonly uploadStartedAt?: string | null;
      readonly uploadCompletedAt?: string | null;
      readonly processingStartedAt?: string | null;
      readonly processingFinishedAt?: string | null;
    },
  ): Promise<void> {
    const current = await this.getSession(id);
    if (!current) {
      throw new Error(`Capture session not found: ${id}`);
    }
    await this.db.runAsync(
      `UPDATE capture_sessions SET
        upload_status = COALESCE(?, upload_status),
        processing_status = COALESCE(?, processing_status),
        backend_job_id = CASE WHEN ? THEN ? ELSE backend_job_id END,
        last_upload_error = CASE WHEN ? THEN ? ELSE last_upload_error END,
        last_processing_error = CASE WHEN ? THEN ? ELSE last_processing_error END,
        upload_started_at = COALESCE(?, upload_started_at),
        upload_completed_at = COALESCE(?, upload_completed_at),
        processing_started_at = COALESCE(?, processing_started_at),
        processing_finished_at = COALESCE(?, processing_finished_at),
        updated_at = ?
       WHERE id = ?;`,
      patch.uploadStatus ?? null,
      patch.processingStatus ?? null,
      patch.backendJobId !== undefined ? 1 : 0,
      patch.backendJobId ?? null,
      patch.lastUploadError !== undefined ? 1 : 0,
      patch.lastUploadError ?? null,
      patch.lastProcessingError !== undefined ? 1 : 0,
      patch.lastProcessingError ?? null,
      patch.uploadStartedAt ?? null,
      patch.uploadCompletedAt ?? null,
      patch.processingStartedAt ?? null,
      patch.processingFinishedAt ?? null,
      new Date().toISOString(),
      id,
    );
  }

  async setPreparationProcessingMode(sessionId: string, mode: string): Promise<void> {
    await this.db.runAsync(
      `UPDATE capture_sessions
       SET preparation_processing_mode = ?, updated_at = ?
       WHERE id = ?;`,
      mode,
      new Date().toISOString(),
      sessionId,
    );
  }

  async repairMultipleOpenSessions(keepSessionId: string, reason: string): Promise<void> {
    const now = new Date().toISOString();
    const placeholders = CAPTURE_EXCLUSIVE_SESSION_STATUSES.map(() => '?').join(', ');
    await this.db.runAsync(
      `UPDATE capture_sessions
       SET status = 'failed', updated_at = ?
       WHERE id <> ? AND status IN (${placeholders});`,
      now,
      keepSessionId,
      ...CAPTURE_EXCLUSIVE_SESSION_STATUSES,
    );
    void reason;
  }

  async updateScanCursor(id: string, cursor: CompositeCursor): Promise<void> {
    await this.db.runAsync(
      'UPDATE capture_sessions SET scan_cursor_date_added = ?, scan_cursor_asset_id = ?, updated_at = ? WHERE id = ?;',
      cursor.dateAdded,
      cursor.assetId,
      new Date().toISOString(),
      id,
    );
  }

  async updateLastValidCursor(id: string, cursor: CompositeCursor): Promise<void> {
    await this.db.runAsync(
      'UPDATE capture_sessions SET last_valid_cursor_date_added = ?, last_valid_cursor_asset_id = ?, updated_at = ? WHERE id = ?;',
      cursor.dateAdded,
      cursor.assetId,
      new Date().toISOString(),
      id,
    );
  }

  /**
   * Persist freeze watermark + exact photo snapshot. Idempotent when fingerprint matches.
   */
  async markCaptureFrozen(
    sessionId: string,
    input: {
      readonly frozenAt: string;
      readonly photoCount: number;
    },
  ): Promise<CaptureSessionRow> {
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_sessions
         SET capture_frozen_at = ?,
             capture_frozen_photo_count = ?,
             capture_freeze_generation = COALESCE(capture_freeze_generation, 0) + 1,
             updated_at = ?
         WHERE id = ?;`,
        input.frozenAt,
        input.photoCount,
        now,
        sessionId,
      ),
    );
    const row = await this.getSession(sessionId);
    if (!row) {
      throw new Error('No se encontró la captura local.');
    }
    return row;
  }

  async createFreezeSnapshot(input: {
    readonly freezeId: string;
    readonly sessionId: string;
    readonly frozenAt: string;
    readonly photoCount: number;
    readonly contentFingerprint: string;
    readonly photos: readonly {
      readonly capturePhotoId: string;
      readonly sequenceNumber: number;
      readonly statusAtFreeze: string;
      readonly included: boolean;
    }[];
  }): Promise<CaptureSessionRow> {
    const now = new Date().toISOString();
    await runImmediateTransaction(this.db, async () => {
      const current = await this.getSession(input.sessionId);
      const nextGen = (current?.capture_freeze_generation ?? 0) + 1;
      await this.db.runAsync(
        `INSERT INTO capture_session_freezes (
          id, capture_session_id, generation, frozen_at, photo_count, content_fingerprint, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);`,
        input.freezeId,
        input.sessionId,
        nextGen,
        input.frozenAt,
        input.photoCount,
        input.contentFingerprint,
        now,
      );
      for (const photo of input.photos) {
        await this.db.runAsync(
          `INSERT INTO capture_session_freeze_photos (
            freeze_id, capture_photo_id, sequence_number, status_at_freeze, included
          ) VALUES (?, ?, ?, ?, ?);`,
          input.freezeId,
          photo.capturePhotoId,
          photo.sequenceNumber,
          photo.statusAtFreeze,
          photo.included ? 1 : 0,
        );
      }
      await this.db.runAsync(
        `UPDATE capture_sessions
         SET capture_frozen_at = ?,
             capture_frozen_photo_count = ?,
             capture_freeze_generation = ?,
             active_freeze_id = ?,
             updated_at = ?
         WHERE id = ?;`,
        input.frozenAt,
        input.photoCount,
        nextGen,
        input.freezeId,
        now,
        input.sessionId,
      );
    });
    const row = await this.getSession(input.sessionId);
    if (!row) {
      throw new Error('No se encontró la captura local.');
    }
    return row;
  }

  async getActiveFreeze(sessionId: string): Promise<{
    readonly id: string;
    readonly generation: number;
    readonly frozen_at: string;
    readonly photo_count: number;
    readonly content_fingerprint: string;
  } | null> {
    const session = await this.getSession(sessionId);
    if (!session?.active_freeze_id) {
      return null;
    }
    return this.db.getFirstAsync(
      `SELECT id, generation, frozen_at, photo_count, content_fingerprint
       FROM capture_session_freezes WHERE id = ?;`,
      session.active_freeze_id,
    );
  }

  async listFreezePhotos(freezeId: string): Promise<CapturePhotoRow[]> {
    const links = await this.db.getAllAsync<{ capture_photo_id: string; sequence_number: number }>(
      `SELECT capture_photo_id, sequence_number
       FROM capture_session_freeze_photos
       WHERE freeze_id = ? AND included = 1
       ORDER BY sequence_number ASC;`,
      freezeId,
    );
    const photos: CapturePhotoRow[] = [];
    for (const link of links) {
      const photo = await this.db.getFirstAsync<CapturePhotoRow>(
        `SELECT * FROM capture_photos WHERE id = ?;`,
        link.capture_photo_id,
      );
      if (photo) {
        photos.push(photo);
      }
    }
    return photos;
  }

  async setUploadPolicy(sessionId: string, policy: 'MANUAL' | 'WHEN_CONNECTED' | 'NOW'): Promise<void> {
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_sessions SET upload_policy = ?, updated_at = ? WHERE id = ?;`,
        policy,
        new Date().toISOString(),
        sessionId,
      ),
    );
  }

  /**
   * Low-level photo upsert. Prefer {@link upsertAdmittedPhotosWithSequences} so
   * sequence_number is assigned at first persist (not at upload time).
   */
  async upsertPhoto(
    sessionId: string,
    image: GalleryImage,
    status: CapturePhotoStatus,
    rejectionReason: string | null = null,
    sequenceNumber: number | null = null,
  ): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `INSERT INTO capture_photos (
        id, capture_session_id, asset_id, media_store_numeric_id, uri, display_name, mime_type,
        size, width, height, date_added, date_modified, bucket_id, relative_path, status,
        rejection_reason, stability_checks, stability_error, detected_at, stable_at, excluded_at,
        upload_status, sequence_number, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_queued', ?, ?, ?)
      ON CONFLICT(capture_session_id, asset_id) DO UPDATE SET
        uri = excluded.uri,
        display_name = excluded.display_name,
        mime_type = excluded.mime_type,
        size = excluded.size,
        width = excluded.width,
        height = excluded.height,
        date_modified = excluded.date_modified,
        status = CASE WHEN capture_photos.status = 'excluded' THEN capture_photos.status ELSE excluded.status END,
        rejection_reason = excluded.rejection_reason,
        stable_at = CASE WHEN excluded.status = 'stable' THEN excluded.updated_at ELSE capture_photos.stable_at END,
        excluded_at = CASE WHEN excluded.status = 'excluded' THEN excluded.updated_at ELSE capture_photos.excluded_at END,
        sequence_number = COALESCE(capture_photos.sequence_number, excluded.sequence_number),
        updated_at = excluded.updated_at;`,
      `${sessionId}:${image.assetId}`,
      sessionId,
      image.assetId,
      image.mediaStoreNumericId ?? null,
      image.uri,
      image.displayName,
      image.mimeType,
      image.size,
      image.width,
      image.height,
      image.dateAdded,
      image.dateModified,
      image.bucketId,
      image.relativePath,
      status,
      rejectionReason,
      0,
      null,
      now,
      status === 'stable' ? now : null,
      status === 'excluded' ? now : null,
      sequenceNumber,
      now,
      now,
    );
  }

  /**
   * Primary sequence assignment path: order the full selection by gallery contract,
   * reserve/assign sequence_number transactionally, then persist. Call before prep.
   * Existing sequence_number values are never recalculated.
   */
  async upsertAdmittedPhotosWithSequences(
    sessionId: string,
    images: readonly GalleryImage[],
    status: CapturePhotoStatus = 'detected',
  ): Promise<void> {
    if (images.length === 0) {
      return;
    }
    const ordered = sortByGalleryOrder(images);
    await runImmediateTransaction(this.db, async () => {
      const maxRow = await this.db.getFirstAsync<{ m: number | null }>(
        `SELECT MAX(sequence_number) AS m FROM capture_photos
           WHERE capture_session_id = ?
             AND sequence_number IS NOT NULL
             AND status != 'excluded'
             AND upload_status NOT IN ('excluded', 'remote_deleted', 'remote_delete_pending');`,
        sessionId,
      );
      let next = maxRow?.m ?? 0;
      for (const image of ordered) {
        const existing = await this.getPhoto(sessionId, image.assetId);
        let sequenceNumber = existing?.sequence_number ?? null;
        if (sequenceNumber == null) {
          next += 1;
          sequenceNumber = next;
        } else if (sequenceNumber > next) {
          next = sequenceNumber;
        }
        await this.upsertPhoto(sessionId, image, status, null, sequenceNumber);
      }
    });
  }

  /**
   * Direct capture: transactionally reserve the next sequence and persist the photo.
   * Equivalent to {@link upsertAdmittedPhotosWithSequences} for a single image.
   */
  async upsertCapturedPhotoWithSequence(
    sessionId: string,
    image: GalleryImage,
    status: CapturePhotoStatus = 'detected',
  ): Promise<void> {
    await this.upsertAdmittedPhotosWithSequences(sessionId, [image], status);
  }

  async updatePhotoStatus(sessionId: string, assetId: string, status: CapturePhotoStatus, error: string | null = null): Promise<void> {
    const current = await this.getPhoto(sessionId, assetId);
    if (!current) {
      throw new Error(`Capture photo not found: ${assetId}`);
    }
    if (!canTransitionPhoto(current.status, status)) {
      throw new Error(`Invalid capture photo transition: ${current.status} -> ${status}`);
    }
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE capture_photos
         SET status = ?, stability_error = ?, stable_at = CASE WHEN ? = 'stable' THEN ? ELSE stable_at END,
             excluded_at = CASE WHEN ? = 'excluded' THEN ? ELSE excluded_at END,
             updated_at = ?
         WHERE capture_session_id = ? AND asset_id = ?;`,
        status,
        error,
        status,
        now,
        status,
        now,
        now,
        sessionId,
        assetId,
      ),
    );
  }

  async ensureClientFileId(sessionId: string, assetId: string, clientFileId: string, uploadBatchId: string): Promise<string> {
    const current = await this.getPhoto(sessionId, assetId);
    if (!current) {
      throw new Error(`Capture photo not found: ${assetId}`);
    }
    if (current.client_file_id) {
      return current.client_file_id;
    }
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
      `UPDATE capture_photos
       SET client_file_id = ?, upload_batch_id = COALESCE(upload_batch_id, ?), updated_at = ?
       WHERE capture_session_id = ? AND asset_id = ? AND client_file_id IS NULL;`,
      clientFileId,
      uploadBatchId,
      new Date().toISOString(),
      sessionId,
      assetId,
      ),
    );
    const updated = await this.getPhoto(sessionId, assetId);
    return updated?.client_file_id ?? clientFileId;
  }

  /**
   * Defensive recovery for legacy rows with NULL sequence_number.
   * Primary assignment is {@link upsertAdmittedPhotosWithSequences} at first persist.
   * Existing values are never recalculated (survives reopen / retry).
   */
  async assignMissingSequenceNumbers(sessionId: string): Promise<void> {
    const photos = await this.db.getAllAsync<Pick<CapturePhotoRow, 'id' | 'sequence_number'>>(
      `SELECT id, sequence_number FROM capture_photos
       WHERE capture_session_id = ?
         AND status = 'stable'
         AND upload_status NOT IN ('excluded', 'remote_deleted')
       ORDER BY date_added ASC, asset_id ASC;`,
      sessionId,
    );
    const assignments = nextSequenceAssignments(photos);
    if (assignments.length === 0) {
      return;
    }
    await runImmediateTransaction(this.db, async () => {
      const now = new Date().toISOString();
      for (const a of assignments) {
        await this.db.runAsync(
          `UPDATE capture_photos
             SET sequence_number = ?, updated_at = ?
             WHERE id = ? AND sequence_number IS NULL;`,
          a.sequenceNumber,
          now,
          a.id,
        );
      }
    });
  }

  /**
   * Seal-time compaction after exclusions leave gaps (backend requires 1..N contiguous).
   *
   * Two-phase update: clear first, then assign. A single-pass UPDATE can hit
   * ``UNIQUE(capture_session_id, sequence_number)`` when an excluded row still
   * holds the target number, or when two active rows swap through the same value.
   */
  async applySequenceCompaction(
    assignments: readonly { readonly id: string; readonly sequenceNumber: number }[],
  ): Promise<number> {
    if (assignments.length === 0) {
      return 0;
    }
    const now = new Date().toISOString();
    await runImmediateTransaction(this.db, async () => {
      for (const a of assignments) {
        await this.db.runAsync(
          `UPDATE capture_photos
             SET sequence_number = NULL, updated_at = ?
             WHERE id = ?;`,
          now,
          a.id,
        );
      }
      for (const a of assignments) {
        await this.db.runAsync(
          `UPDATE capture_photos
             SET sequence_number = ?, updated_at = ?
             WHERE id = ?;`,
          a.sequenceNumber,
          now,
          a.id,
        );
      }
    });
    return assignments.length;
  }

  /** Release sequence slots held by excluded / remote-deleted photos. */
  async clearSequenceNumbersForExcluded(sessionId: string): Promise<number> {
    const result = await withSqliteBusyRetry(() =>
      this.db.runAsync(
      `UPDATE capture_photos
       SET sequence_number = NULL, updated_at = ?
       WHERE capture_session_id = ?
         AND sequence_number IS NOT NULL
         AND (
           status = 'excluded'
           OR upload_status IN ('excluded', 'remote_deleted', 'remote_delete_pending')
         );`,
      new Date().toISOString(),
      sessionId,
      ),
    );
    return result.changes ?? 0;
  }

  async clearPhotoSequenceNumber(photoId: string): Promise<void> {
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
      `UPDATE capture_photos
       SET sequence_number = NULL, updated_at = ?
       WHERE id = ?;`,
      new Date().toISOString(),
      photoId,
      ),
    );
  }

  async setBackendOrderedCaptureSessionId(sessionId: string, orderedCaptureSessionId: string): Promise<void> {
    await this.db.runAsync(
      `UPDATE capture_sessions
       SET backend_ordered_capture_session_id = COALESCE(backend_ordered_capture_session_id, ?),
           updated_at = ?
       WHERE id = ?;`,
      orderedCaptureSessionId,
      new Date().toISOString(),
      sessionId,
    );
  }

  async setPhotoUploadStatus(
    photoId: string,
    status: PhotoUploadStatus,
    patch: {
      readonly progress?: number;
      readonly backendAssetId?: string | null;
      readonly errorCode?: string | null;
      readonly errorMessage?: string | null;
      readonly nextRetryAt?: string | null;
      readonly incrementAttempts?: boolean;
      readonly uploadedAt?: string | null;
      readonly remoteDeletedAt?: string | null;
      readonly localTransformUri?: string | null;
      readonly originalSize?: number | null;
      readonly uploadSize?: number | null;
    } = {},
  ): Promise<void> {
    const now = new Date().toISOString();
    const clearLease = [
      'uploaded',
      'excluded',
      'permanent_error',
      'remote_deleted',
      'remote_delete_pending',
    ].includes(status);
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
      `UPDATE capture_photos SET
        upload_status = ?,
        upload_progress = COALESCE(?, upload_progress),
        backend_asset_id = COALESCE(?, backend_asset_id),
        last_upload_error_code = ?,
        last_upload_error_message = ?,
        last_upload_attempt_at = CASE WHEN ? THEN ? ELSE last_upload_attempt_at END,
        upload_attempts = CASE WHEN ? THEN upload_attempts + 1 ELSE upload_attempts END,
        next_retry_at = ?,
        uploaded_at = COALESCE(?, uploaded_at),
        remote_deleted_at = COALESCE(?, remote_deleted_at),
        local_transform_uri = CASE WHEN ? THEN ? ELSE local_transform_uri END,
        original_size = COALESCE(?, original_size),
        upload_size = CASE WHEN ? THEN ? ELSE upload_size END,
        upload_worker_owner = CASE WHEN ? THEN NULL ELSE upload_worker_owner END,
        upload_lease_token = CASE WHEN ? THEN NULL ELSE upload_lease_token END,
        upload_lease_expires_at = CASE WHEN ? THEN NULL ELSE upload_lease_expires_at END,
        upload_heartbeat_at = CASE WHEN ? THEN NULL ELSE upload_heartbeat_at END,
        upload_cancel_requested = CASE WHEN ? THEN 0 ELSE upload_cancel_requested END,
        updated_at = ?
       WHERE id = ?;`,
      status,
      patch.progress ?? null,
      patch.backendAssetId ?? null,
      patch.errorCode ?? null,
      patch.errorMessage ?? null,
      patch.incrementAttempts ? 1 : 0,
      now,
      patch.incrementAttempts ? 1 : 0,
      patch.nextRetryAt ?? null,
      patch.uploadedAt ?? null,
      patch.remoteDeletedAt ?? null,
      patch.localTransformUri !== undefined ? 1 : 0,
      patch.localTransformUri ?? null,
      patch.originalSize ?? null,
      patch.uploadSize !== undefined ? 1 : 0,
      patch.uploadSize ?? null,
      clearLease ? 1 : 0,
      clearLease ? 1 : 0,
      clearLease ? 1 : 0,
      clearLease ? 1 : 0,
      clearLease ? 1 : 0,
      now,
      photoId,
      ),
    );
  }

  /**
   * Transactional lease acquire. Returns true only when this owner won the row.
   * Allows reclaim when lease is missing/expired or the same token renews.
   */
  async tryAcquireUploadLease(input: {
    readonly photoId: string;
    readonly owner: string;
    readonly token: string;
    readonly expiresAt: string;
    readonly nowIso?: string;
  }): Promise<boolean> {
    const now = input.nowIso ?? new Date().toISOString();
    const result = await this.db.runAsync(
      `UPDATE capture_photos SET
        upload_worker_owner = ?,
        upload_lease_token = ?,
        upload_lease_expires_at = ?,
        upload_heartbeat_at = ?,
        updated_at = ?
       WHERE id = ?
         AND upload_status IN ('queued', 'retryable_error', 'uploading')
         AND COALESCE(upload_cancel_requested, 0) = 0
         AND (
           upload_lease_token IS NULL
           OR upload_lease_expires_at IS NULL
           OR upload_lease_expires_at <= ?
           OR upload_lease_token = ?
         );`,
      input.owner,
      input.token,
      input.expiresAt,
      now,
      now,
      input.photoId,
      now,
      input.token,
    );
    return (result.changes ?? 0) === 1;
  }

  async heartbeatUploadLease(photoId: string, token: string, expiresAt: string): Promise<boolean> {
    const now = new Date().toISOString();
    const result = await this.db.runAsync(
      `UPDATE capture_photos SET
        upload_lease_expires_at = ?,
        upload_heartbeat_at = ?,
        updated_at = ?
       WHERE id = ?
         AND upload_lease_token = ?;`,
      expiresAt,
      now,
      now,
      photoId,
      token,
    );
    return (result.changes ?? 0) === 1;
  }

  async releaseUploadLease(photoId: string, token: string | null): Promise<void> {
    const now = new Date().toISOString();
    if (token) {
      await this.db.runAsync(
        `UPDATE capture_photos SET
          upload_worker_owner = NULL,
          upload_lease_token = NULL,
          upload_lease_expires_at = NULL,
          upload_heartbeat_at = NULL,
          updated_at = ?
         WHERE id = ? AND (upload_lease_token = ? OR upload_lease_token IS NULL);`,
        now,
        photoId,
        token,
      );
      return;
    }
    await this.db.runAsync(
      `UPDATE capture_photos SET
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
       WHERE id = ?;`,
      now,
      photoId,
    );
  }

  async setUploadCancelRequested(photoId: string, requested: boolean): Promise<void> {
    await this.db.runAsync(
      `UPDATE capture_photos SET upload_cancel_requested = ?, updated_at = ? WHERE id = ?;`,
      requested ? 1 : 0,
      new Date().toISOString(),
      photoId,
    );
  }

  async listPhotosForUpload(sessionId: string): Promise<CapturePhotoRow[]> {
    return this.db.getAllAsync<CapturePhotoRow>(
      `SELECT * FROM capture_photos
       WHERE capture_session_id = ?
         AND status = 'stable'
         AND upload_status IN ('queued', 'preparing', 'uploading', 'retryable_error')
       ORDER BY date_added ASC, asset_id ASC;`,
      sessionId,
    );
  }

  async listStableNotQueued(sessionId: string): Promise<CapturePhotoRow[]> {
    return this.db.getAllAsync<CapturePhotoRow>(
      `SELECT * FROM capture_photos
       WHERE capture_session_id = ?
         AND status = 'stable'
         AND upload_status = 'not_queued'
       ORDER BY date_added ASC, asset_id ASC;`,
      sessionId,
    );
  }

  async applyStabilityResult(
    input: StabilityResultInput,
    options?: {
      readonly onBusyRetry?: (info: { readonly attempt: number; readonly maxAttempts: number }) => void;
    },
  ): Promise<boolean> {
    const current = await this.getPhoto(input.sessionId, input.assetId);
    if (!current) {
      return false;
    }
    if (!canTransitionPhoto(current.status, input.status)) {
      return false;
    }
    const now = new Date().toISOString();
    const result = await withSqliteBusyRetry(
      () =>
        this.db.runAsync(
          `UPDATE capture_photos
         SET status = ?,
             stability_error = ?,
             stability_checks = ?,
             stability_attempts = stability_attempts + 1,
             last_stability_attempt_at = ?,
             stable_at = CASE WHEN ? = 'stable' THEN ? ELSE stable_at END,
             updated_at = ?
         WHERE capture_session_id = ?
           AND asset_id = ?
           AND status IN ('detected', 'waiting_stability');`,
          input.status,
          input.error,
          input.checks,
          now,
          input.status,
          now,
          now,
          input.sessionId,
          input.assetId,
        ),
      options?.onBusyRetry ? { onBusyRetry: options.onBusyRetry } : {},
    ) as { changes?: number };
    return (result.changes ?? 0) > 0;
  }

  async markValidationInterrupted(
    sessionId: string,
    assetId: string,
    error: 'validation_interrupted' | 'validation_timeout',
  ): Promise<boolean> {
    const now = new Date().toISOString();
    const result = await this.db.runAsync(
      `UPDATE capture_photos
       SET status = 'unstable',
           stability_error = ?,
           stability_attempts = stability_attempts + 1,
           last_stability_attempt_at = ?,
           updated_at = ?
       WHERE capture_session_id = ?
         AND asset_id = ?
         AND status IN ('detected', 'waiting_stability');`,
      error,
      now,
      now,
      sessionId,
      assetId,
    ) as { changes?: number };
    return (result.changes ?? 0) > 0;
  }

  async getPhoto(sessionId: string, assetId: string): Promise<CapturePhotoRow | null> {
    return this.db.getFirstAsync<CapturePhotoRow>(
      'SELECT * FROM capture_photos WHERE capture_session_id = ? AND asset_id = ?;',
      sessionId,
      assetId,
    );
  }

  async getPhotoById(photoId: string): Promise<CapturePhotoRow | null> {
    return this.db.getFirstAsync<CapturePhotoRow>('SELECT * FROM capture_photos WHERE id = ?;', photoId);
  }

  async listPhotos(sessionId: string): Promise<CapturePhotoRow[]> {
    return this.db.getAllAsync<CapturePhotoRow>(
      'SELECT * FROM capture_photos WHERE capture_session_id = ? ORDER BY date_added ASC, asset_id ASC;',
      sessionId,
    );
  }

  async inspectedAssetIds(sessionId: string): Promise<Set<string>> {
    const rows = await this.db.getAllAsync<{ asset_id: string }>(
      'SELECT asset_id FROM capture_photos WHERE capture_session_id = ?;',
      sessionId,
    );
    return new Set(rows.map((r) => r.asset_id));
  }
}
