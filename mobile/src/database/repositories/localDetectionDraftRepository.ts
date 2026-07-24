import type { SQLiteDatabase } from '../database';
import { createId } from '../../shared/createId';

export type LocalDetectionDraftStatus =
  | 'NOT_APPLICABLE'
  | 'PENDING'
  | 'SCANNING'
  | 'RESOLVED'
  | 'UNRESOLVED'
  | 'INVALID'
  | 'AMBIGUOUS'
  | 'FAILED'
  | 'FAILED_RETRYABLE'
  | 'DETECTED_UNVERIFIED';

/** comparison_status: open until a reliable mapping exists. */
export type LocalComparisonStatus = 'PENDING' | 'MAPPED' | 'SKIPPED' | null;

/** Sync lifecycle — independent from scan status. */
export type LocalDraftSyncStatus =
  | 'NOT_READY'
  | 'PENDING'
  | 'SYNCING'
  | 'SYNCED'
  | 'RETRY_SCHEDULED'
  | 'REJECTED'
  | 'CONFLICT'
  | 'FAILED_TERMINAL';

export interface LocalDetectionDraftRow {
  readonly id: string;
  readonly capture_photo_id: string;
  readonly capture_session_id: string;
  readonly client_file_id: string | null;
  readonly status: LocalDetectionDraftStatus;
  readonly raw_value_hash: string | null;
  readonly internal_code: string | null;
  readonly quantity: number | null;
  readonly quantity_status: string | null;
  readonly detected_format: string | null;
  readonly detected_symbology: string | null;
  readonly parser_version: string;
  readonly detector_version: string;
  readonly candidate_count: number;
  readonly error_code: string | null;
  readonly processing_ms: number | null;
  readonly comparison_status: string | null;
  readonly compare_result: string | null;
  readonly compared_at: string | null;
  readonly prepared_asset_fingerprint: string | null;
  readonly scan_owner: string | null;
  readonly scan_generation: number;
  readonly sync_status: LocalDraftSyncStatus;
  readonly sync_attempt_count: number;
  readonly sync_next_retry_at: string | null;
  readonly sync_last_error_code: string | null;
  readonly server_preliminary_id: string | null;
  readonly synced_at: string | null;
  readonly sync_lease_token: string | null;
  readonly sync_lease_expires_at: string | null;
  readonly detected_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class LocalDetectionDraftRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async upsertDraft(input: {
    readonly capturePhotoId: string;
    readonly captureSessionId: string;
    readonly clientFileId: string | null;
    readonly status: LocalDetectionDraftStatus;
    readonly rawValueHash?: string | null;
    readonly internalCode?: string | null;
    readonly quantity?: number | null;
    readonly quantityStatus?: string | null;
    readonly detectedFormat?: string | null;
    readonly detectedSymbology?: string | null;
    readonly parserVersion: string;
    readonly detectorVersion: string;
    readonly candidateCount?: number;
    readonly errorCode?: string | null;
    readonly processingMs?: number | null;
    readonly preparedAssetFingerprint: string;
    readonly scanOwner?: string | null;
    readonly scanGeneration?: number;
    readonly comparisonStatus?: string | null;
    readonly detectedAt?: string | null;
  }): Promise<LocalDetectionDraftRow> {
    const now = new Date().toISOString();
    const id = createId();
    const generation = input.scanGeneration ?? 0;
    const terminal =
      input.status !== 'PENDING' &&
      input.status !== 'SCANNING' &&
      input.status !== 'NOT_APPLICABLE';
    const detectedAt = terminal ? (input.detectedAt ?? now) : null;
    await this.db.runAsync(
      `INSERT INTO local_detection_drafts (
        id, capture_photo_id, capture_session_id, client_file_id, status,
        raw_value_hash, internal_code, quantity, quantity_status,
        detected_format, detected_symbology, parser_version, detector_version,
        candidate_count, error_code, processing_ms, comparison_status, compare_result, compared_at,
        prepared_asset_fingerprint, scan_owner, scan_generation, detected_at, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(capture_photo_id, detector_version, parser_version, prepared_asset_fingerprint)
      DO UPDATE SET
        status = excluded.status,
        client_file_id = excluded.client_file_id,
        raw_value_hash = excluded.raw_value_hash,
        internal_code = excluded.internal_code,
        quantity = excluded.quantity,
        quantity_status = excluded.quantity_status,
        detected_format = excluded.detected_format,
        detected_symbology = excluded.detected_symbology,
        candidate_count = excluded.candidate_count,
        error_code = excluded.error_code,
        processing_ms = excluded.processing_ms,
        comparison_status = COALESCE(excluded.comparison_status, local_detection_drafts.comparison_status),
        scan_owner = excluded.scan_owner,
        scan_generation = CASE
          WHEN excluded.scan_generation >= local_detection_drafts.scan_generation
          THEN excluded.scan_generation
          ELSE local_detection_drafts.scan_generation
        END,
        detected_at = COALESCE(local_detection_drafts.detected_at, excluded.detected_at),
        updated_at = excluded.updated_at
      WHERE excluded.scan_generation >= local_detection_drafts.scan_generation;`,
      id,
      input.capturePhotoId,
      input.captureSessionId,
      input.clientFileId,
      input.status,
      input.rawValueHash ?? null,
      input.internalCode ?? null,
      input.quantity ?? null,
      input.quantityStatus ?? null,
      input.detectedFormat ?? null,
      input.detectedSymbology ?? null,
      input.parserVersion,
      input.detectorVersion,
      input.candidateCount ?? 0,
      input.errorCode ?? null,
      input.processingMs ?? null,
      input.comparisonStatus ?? null,
      input.preparedAssetFingerprint,
      input.scanOwner ?? null,
      generation,
      detectedAt,
      now,
      now,
    );
    const row = await this.getByIdempotencyKey(
      input.capturePhotoId,
      input.detectorVersion,
      input.parserVersion,
      input.preparedAssetFingerprint,
    );
    if (!row) {
      throw new Error('Failed to persist local detection draft');
    }
    return row;
  }

  async getByIdempotencyKey(
    capturePhotoId: string,
    detectorVersion: string,
    parserVersion: string,
    preparedAssetFingerprint: string,
  ): Promise<LocalDetectionDraftRow | null> {
    return this.db.getFirstAsync<LocalDetectionDraftRow>(
      `SELECT * FROM local_detection_drafts
       WHERE capture_photo_id = ?
         AND detector_version = ?
         AND parser_version = ?
         AND prepared_asset_fingerprint = ?
       LIMIT 1;`,
      capturePhotoId,
      detectorVersion,
      parserVersion,
      preparedAssetFingerprint,
    );
  }

  async listForSession(sessionId: string): Promise<LocalDetectionDraftRow[]> {
    return this.db.getAllAsync<LocalDetectionDraftRow>(
      `SELECT * FROM local_detection_drafts
       WHERE capture_session_id = ?
       ORDER BY created_at ASC;`,
      sessionId,
    );
  }

  async listForPhoto(capturePhotoId: string): Promise<LocalDetectionDraftRow[]> {
    return this.db.getAllAsync<LocalDetectionDraftRow>(
      `SELECT * FROM local_detection_drafts
       WHERE capture_photo_id = ?
       ORDER BY updated_at DESC;`,
      capturePhotoId,
    );
  }

  async listStaleScanning(olderThanIso: string): Promise<LocalDetectionDraftRow[]> {
    return this.db.getAllAsync<LocalDetectionDraftRow>(
      `SELECT * FROM local_detection_drafts
       WHERE status = 'SCANNING' AND updated_at < ?;`,
      olderThanIso,
    );
  }

  async recoverStaleScanning(olderThanIso: string): Promise<number> {
    const now = new Date().toISOString();
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET status = 'FAILED_RETRYABLE',
           error_code = 'SCANNING_LEASE_EXPIRED',
           scan_owner = NULL,
           updated_at = ?
       WHERE status = 'SCANNING' AND updated_at < ?;`,
      now,
      olderThanIso,
    );
    return result.changes ?? 0;
  }

  /** Mark comparison complete only when mapping is reliable. */
  async markCompared(id: string, compareResult: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET compare_result = ?, compared_at = ?, comparison_status = 'MAPPED', updated_at = ?
       WHERE id = ?;`,
      compareResult,
      now,
      now,
      id,
    );
  }

  async markComparisonMappingUnavailable(sessionId: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET comparison_status = 'PENDING', updated_at = ?
       WHERE capture_session_id = ?
         AND status NOT IN ('NOT_APPLICABLE')
         AND compared_at IS NULL;`,
      now,
      sessionId,
    );
  }

  async deleteForSession(sessionId: string): Promise<void> {
    await this.db.runAsync(`DELETE FROM local_detection_drafts WHERE capture_session_id = ?;`, sessionId);
  }

  async deleteForPhoto(capturePhotoId: string): Promise<void> {
    await this.db.runAsync(`DELETE FROM local_detection_drafts WHERE capture_photo_id = ?;`, capturePhotoId);
  }

  async deleteAll(): Promise<void> {
    await this.db.runAsync(`DELETE FROM local_detection_drafts;`);
  }

  async isScanInFlightForPhoto(capturePhotoId: string): Promise<boolean> {
    const row = await this.db.getFirstAsync<{ c: number }>(
      `SELECT COUNT(*) AS c FROM local_detection_drafts
       WHERE capture_photo_id = ? AND status IN ('PENDING', 'SCANNING');`,
      capturePhotoId,
    );
    return (row?.c ?? 0) > 0;
  }

  async getById(id: string): Promise<LocalDetectionDraftRow | null> {
    return this.db.getFirstAsync<LocalDetectionDraftRow>(
      `SELECT * FROM local_detection_drafts WHERE id = ? LIMIT 1;`,
      id,
    );
  }

  /**
   * Mark terminal drafts for a photo as PENDING once the remote asset exists.
   * Does not touch SYNCED / REJECTED / CONFLICT / FAILED_TERMINAL.
   */
  async markPendingForPhotoWhenReady(capturePhotoId: string): Promise<number> {
    const now = new Date().toISOString();
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = 'PENDING',
           sync_next_retry_at = NULL,
           updated_at = ?
       WHERE capture_photo_id = ?
         AND status NOT IN ('PENDING', 'SCANNING', 'NOT_APPLICABLE')
         AND sync_status IN ('NOT_READY', 'RETRY_SCHEDULED')
         AND prepared_asset_fingerprint IS NOT NULL
         AND client_file_id IS NOT NULL;`,
      now,
      capturePhotoId,
    );
    return result.changes ?? 0;
  }

  async listDueForSync(nowIso: string, limit: number): Promise<LocalDetectionDraftRow[]> {
    return this.db.getAllAsync<LocalDetectionDraftRow>(
      `SELECT * FROM local_detection_drafts
       WHERE sync_status IN ('PENDING', 'RETRY_SCHEDULED')
         AND (sync_next_retry_at IS NULL OR sync_next_retry_at <= ?)
         AND status NOT IN ('PENDING', 'SCANNING', 'NOT_APPLICABLE')
       ORDER BY created_at ASC
       LIMIT ?;`,
      nowIso,
      limit,
    );
  }

  async claimSyncLease(
    draftId: string,
    leaseToken: string,
    leaseExpiresAt: string,
    nowIso: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = 'SYNCING',
           sync_lease_token = ?,
           sync_lease_expires_at = ?,
           sync_attempt_count = sync_attempt_count + 1,
           updated_at = ?
       WHERE id = ?
         AND sync_status IN ('PENDING', 'RETRY_SCHEDULED')
         AND (
           sync_lease_token IS NULL
           OR sync_lease_expires_at IS NULL
           OR sync_lease_expires_at <= ?
           OR sync_lease_token = ?
         );`,
      leaseToken,
      leaseExpiresAt,
      nowIso,
      draftId,
      nowIso,
      leaseToken,
    );
    return (result.changes ?? 0) > 0;
  }

  async completeSyncSuccess(
    draftId: string,
    leaseToken: string,
    serverPreliminaryId: string,
    syncedAt: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = 'SYNCED',
           server_preliminary_id = ?,
           synced_at = ?,
           sync_last_error_code = NULL,
           sync_next_retry_at = NULL,
           sync_lease_token = NULL,
           sync_lease_expires_at = NULL,
           updated_at = ?
       WHERE id = ? AND sync_lease_token = ?;`,
      serverPreliminaryId,
      syncedAt,
      syncedAt,
      draftId,
      leaseToken,
    );
    return (result.changes ?? 0) > 0;
  }

  async completeSyncTerminal(
    draftId: string,
    leaseToken: string,
    syncStatus: 'REJECTED' | 'CONFLICT' | 'FAILED_TERMINAL',
    errorCode: string,
    nowIso: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = ?,
           sync_last_error_code = ?,
           sync_next_retry_at = NULL,
           sync_lease_token = NULL,
           sync_lease_expires_at = NULL,
           updated_at = ?
       WHERE id = ? AND sync_lease_token = ?;`,
      syncStatus,
      errorCode,
      nowIso,
      draftId,
      leaseToken,
    );
    return (result.changes ?? 0) > 0;
  }

  async completeSyncRetry(
    draftId: string,
    leaseToken: string,
    errorCode: string,
    nextRetryAt: string,
    nowIso: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = 'RETRY_SCHEDULED',
           sync_last_error_code = ?,
           sync_next_retry_at = ?,
           sync_lease_token = NULL,
           sync_lease_expires_at = NULL,
           updated_at = ?
       WHERE id = ? AND sync_lease_token = ?;`,
      errorCode,
      nextRetryAt,
      nowIso,
      draftId,
      leaseToken,
    );
    return (result.changes ?? 0) > 0;
  }

  async recoverExpiredSyncLeases(nowIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = 'RETRY_SCHEDULED',
           sync_last_error_code = 'SYNC_LEASE_EXPIRED',
           sync_lease_token = NULL,
           sync_lease_expires_at = NULL,
           updated_at = ?
       WHERE sync_status = 'SYNCING'
         AND sync_lease_expires_at IS NOT NULL
         AND sync_lease_expires_at <= ?;`,
      nowIso,
      nowIso,
    );
    return result.changes ?? 0;
  }

  async getEarliestSyncRetryAt(): Promise<string | null> {
    const row = await this.db.getFirstAsync<{ next_at: string | null }>(
      `SELECT MIN(
          CASE
            WHEN sync_status = 'PENDING' THEN COALESCE(sync_next_retry_at, created_at)
            WHEN sync_status = 'RETRY_SCHEDULED' THEN sync_next_retry_at
            ELSE NULL
          END
        ) AS next_at
       FROM local_detection_drafts
       WHERE sync_status IN ('PENDING', 'RETRY_SCHEDULED');`,
    );
    return row?.next_at ?? null;
  }

  async markNotReady(
    draftId: string,
    errorCode: string,
    nowIso: string,
  ): Promise<void> {
    await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET sync_status = 'NOT_READY',
           sync_last_error_code = ?,
           sync_lease_token = NULL,
           sync_lease_expires_at = NULL,
           sync_next_retry_at = NULL,
           updated_at = ?
       WHERE id = ?;`,
      errorCode,
      nowIso,
      draftId,
    );
  }

  async purgeSyncedOlderThan(cutoffIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `DELETE FROM local_detection_drafts
       WHERE sync_status = 'SYNCED'
         AND synced_at IS NOT NULL
         AND synced_at < ?;`,
      cutoffIso,
    );
    return result.changes ?? 0;
  }

  async purgeTerminalOlderThan(cutoffIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `DELETE FROM local_detection_drafts
       WHERE sync_status IN ('REJECTED', 'CONFLICT', 'FAILED_TERMINAL')
         AND updated_at < ?;`,
      cutoffIso,
    );
    return result.changes ?? 0;
  }
}
