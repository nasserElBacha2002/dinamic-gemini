import type { SQLiteDatabase } from '../database';
import { createId } from '../../shared/createId';

export type ConfirmedQuantityStatus = 'PRESENT' | 'MISSING';
export type ConfirmedLocalResultSource = 'LOCAL_CODE_SCAN' | 'LOCAL_MANUAL_CORRECTION';

export type ConfirmedLocalResultSyncStatus =
  | 'PENDING'
  | 'SYNCING'
  | 'SYNCED'
  | 'RETRY_SCHEDULED'
  | 'CONFLICT'
  | 'REJECTED'
  | 'FAILED_TERMINAL';

export interface ConfirmedLocalResultRow {
  readonly id: string;
  readonly capture_photo_id: string;
  readonly capture_session_id: string;
  readonly client_file_id: string | null;
  readonly asset_id: string | null;
  readonly detected_internal_code: string | null;
  readonly detected_quantity: number | null;
  readonly confirmed_internal_code: string;
  readonly confirmed_quantity: number | null;
  readonly quantity_status: ConfirmedQuantityStatus;
  readonly source: ConfirmedLocalResultSource;
  readonly detected_symbology: string | null;
  readonly parser_version: string;
  readonly detector_version: string;
  readonly prepared_asset_sha256: string;
  readonly confirmed_by_user_id: string | null;
  readonly confirmed_at: string;
  readonly sync_status: ConfirmedLocalResultSyncStatus;
  readonly sync_attempt_count: number;
  readonly next_retry_at: string | null;
  readonly sync_last_error_code: string | null;
  readonly row_version: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export class ConfirmedLocalResultRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async upsertConfirmed(input: {
    readonly capturePhotoId: string;
    readonly captureSessionId: string;
    readonly clientFileId: string | null;
    readonly assetId?: string | null;
    readonly detectedInternalCode: string | null;
    readonly detectedQuantity: number | null;
    readonly confirmedInternalCode: string;
    readonly confirmedQuantity: number | null;
    readonly quantityStatus: ConfirmedQuantityStatus;
    readonly source: ConfirmedLocalResultSource;
    readonly detectedSymbology: string | null;
    readonly parserVersion: string;
    readonly detectorVersion: string;
    readonly preparedAssetSha256: string;
    readonly confirmedByUserId: string | null;
    readonly confirmedAt: string;
  }): Promise<ConfirmedLocalResultRow> {
    const now = new Date().toISOString();
    const existing = await this.getByPhotoId(input.capturePhotoId);
    if (existing) {
      const rowVersion = existing.row_version + 1;
      await this.db.runAsync(
        `UPDATE confirmed_local_results SET
          client_file_id = ?,
          detected_internal_code = ?,
          detected_quantity = ?,
          confirmed_internal_code = ?,
          confirmed_quantity = ?,
          quantity_status = ?,
          source = ?,
          detected_symbology = ?,
          parser_version = ?,
          detector_version = ?,
          prepared_asset_sha256 = ?,
          confirmed_by_user_id = ?,
          confirmed_at = ?,
          sync_status = 'PENDING',
          sync_attempt_count = 0,
          next_retry_at = NULL,
          sync_last_error_code = NULL,
          row_version = ?,
          updated_at = ?
        WHERE capture_photo_id = ?;`,
        input.clientFileId,
        input.detectedInternalCode,
        input.detectedQuantity,
        input.confirmedInternalCode,
        input.confirmedQuantity,
        input.quantityStatus,
        input.source,
        input.detectedSymbology,
        input.parserVersion,
        input.detectorVersion,
        input.preparedAssetSha256,
        input.confirmedByUserId,
        input.confirmedAt,
        rowVersion,
        now,
        input.capturePhotoId,
      );
      const row = await this.getByPhotoId(input.capturePhotoId);
      if (!row) {
        throw new Error('Failed to update confirmed local result');
      }
      return row;
    }

    const id = createId();
    await this.db.runAsync(
      `INSERT INTO confirmed_local_results (
        id, capture_photo_id, capture_session_id, client_file_id, asset_id,
        detected_internal_code, detected_quantity, confirmed_internal_code, confirmed_quantity,
        quantity_status, source, detected_symbology, parser_version, detector_version,
        prepared_asset_sha256, confirmed_by_user_id, confirmed_at,
        sync_status, sync_attempt_count, next_retry_at, sync_last_error_code,
        row_version, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0, NULL, NULL, 1, ?, ?);`,
      id,
      input.capturePhotoId,
      input.captureSessionId,
      input.clientFileId,
      input.assetId ?? null,
      input.detectedInternalCode,
      input.detectedQuantity,
      input.confirmedInternalCode,
      input.confirmedQuantity,
      input.quantityStatus,
      input.source,
      input.detectedSymbology,
      input.parserVersion,
      input.detectorVersion,
      input.preparedAssetSha256,
      input.confirmedByUserId,
      input.confirmedAt,
      now,
      now,
    );
    const row = await this.getByPhotoId(input.capturePhotoId);
    if (!row) {
      throw new Error('Failed to persist confirmed local result');
    }
    return row;
  }

  async getByPhotoId(capturePhotoId: string): Promise<ConfirmedLocalResultRow | null> {
    return this.db.getFirstAsync<ConfirmedLocalResultRow>(
      `SELECT * FROM confirmed_local_results WHERE capture_photo_id = ? LIMIT 1;`,
      capturePhotoId,
    );
  }

  async getById(id: string): Promise<ConfirmedLocalResultRow | null> {
    return this.db.getFirstAsync<ConfirmedLocalResultRow>(
      `SELECT * FROM confirmed_local_results WHERE id = ? LIMIT 1;`,
      id,
    );
  }

  async listForSession(sessionId: string): Promise<ConfirmedLocalResultRow[]> {
    return this.db.getAllAsync<ConfirmedLocalResultRow>(
      `SELECT * FROM confirmed_local_results
       WHERE capture_session_id = ?
       ORDER BY created_at ASC;`,
      sessionId,
    );
  }

  async markPendingForPhotoWhenReady(capturePhotoId: string): Promise<number> {
    const now = new Date().toISOString();
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = 'PENDING',
           next_retry_at = NULL,
           updated_at = ?
       WHERE capture_photo_id = ?
         AND sync_status IN ('RETRY_SCHEDULED')
         AND client_file_id IS NOT NULL
         AND prepared_asset_sha256 IS NOT NULL;`,
      now,
      capturePhotoId,
    );
    return result.changes ?? 0;
  }

  async setAssetIdForPhoto(capturePhotoId: string, assetId: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET asset_id = ?, updated_at = ?
       WHERE capture_photo_id = ?;`,
      assetId,
      now,
      capturePhotoId,
    );
  }

  async listDueForSync(nowIso: string, limit: number): Promise<ConfirmedLocalResultRow[]> {
    return this.db.getAllAsync<ConfirmedLocalResultRow>(
      `SELECT * FROM confirmed_local_results
       WHERE sync_status IN ('PENDING', 'RETRY_SCHEDULED')
         AND (next_retry_at IS NULL OR next_retry_at <= ?)
       ORDER BY created_at ASC
       LIMIT ?;`,
      nowIso,
      limit,
    );
  }

  async claimSyncLease(
    resultId: string,
    leaseToken: string,
    leaseExpiresAt: string,
    nowIso: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = 'SYNCING',
           sync_attempt_count = sync_attempt_count + 1,
           updated_at = ?
       WHERE id = ?
         AND sync_status IN ('PENDING', 'RETRY_SCHEDULED');`,
      nowIso,
      resultId,
    );
    void leaseToken;
    void leaseExpiresAt;
    return (result.changes ?? 0) > 0;
  }

  async completeSyncSuccess(resultId: string, syncedAt: string): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = 'SYNCED',
           sync_last_error_code = NULL,
           next_retry_at = NULL,
           updated_at = ?
       WHERE id = ? AND sync_status = 'SYNCING';`,
      syncedAt,
      resultId,
    );
    return (result.changes ?? 0) > 0;
  }

  async completeSyncTerminal(
    resultId: string,
    syncStatus: 'REJECTED' | 'CONFLICT' | 'FAILED_TERMINAL',
    errorCode: string,
    nowIso: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = ?,
           sync_last_error_code = ?,
           next_retry_at = NULL,
           updated_at = ?
       WHERE id = ? AND sync_status = 'SYNCING';`,
      syncStatus,
      errorCode,
      nowIso,
      resultId,
    );
    return (result.changes ?? 0) > 0;
  }

  async completeSyncRetry(
    resultId: string,
    errorCode: string,
    nextRetryAt: string,
    nowIso: string,
  ): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = 'RETRY_SCHEDULED',
           sync_last_error_code = ?,
           next_retry_at = ?,
           updated_at = ?
       WHERE id = ? AND sync_status = 'SYNCING';`,
      errorCode,
      nextRetryAt,
      nowIso,
      resultId,
    );
    return (result.changes ?? 0) > 0;
  }

  async resetToPending(resultId: string, errorCode: string, nowIso: string): Promise<boolean> {
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = 'PENDING',
           sync_last_error_code = ?,
           next_retry_at = NULL,
           updated_at = ?
       WHERE id = ? AND sync_status = 'SYNCING';`,
      errorCode,
      nowIso,
      resultId,
    );
    return (result.changes ?? 0) > 0;
  }

  async markNotReady(resultId: string, errorCode: string, nowIso: string): Promise<void> {
    await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_last_error_code = ?,
           next_retry_at = NULL,
           updated_at = ?
       WHERE id = ?;`,
      errorCode,
      nowIso,
      resultId,
    );
  }

  async recoverExpiredSyncLeases(nowIso: string): Promise<number> {
    const result = await this.db.runAsync(
      `UPDATE confirmed_local_results
       SET sync_status = 'RETRY_SCHEDULED',
           sync_last_error_code = 'SYNC_LEASE_EXPIRED',
           next_retry_at = ?,
           updated_at = ?
       WHERE sync_status = 'SYNCING';`,
      nowIso,
      nowIso,
    );
    return result.changes ?? 0;
  }

  async getEarliestSyncRetryAt(): Promise<string | null> {
    const row = await this.db.getFirstAsync<{ next_at: string | null }>(
      `SELECT MIN(
          CASE
            WHEN sync_status = 'PENDING' THEN COALESCE(next_retry_at, created_at)
            WHEN sync_status = 'RETRY_SCHEDULED' THEN next_retry_at
            ELSE NULL
          END
        ) AS next_at
       FROM confirmed_local_results
       WHERE sync_status IN ('PENDING', 'RETRY_SCHEDULED');`,
    );
    return row?.next_at ?? null;
  }

  async deleteForSession(sessionId: string): Promise<void> {
    await this.db.runAsync(`DELETE FROM confirmed_local_results WHERE capture_session_id = ?;`, sessionId);
  }

  async deleteAll(): Promise<void> {
    await this.db.runAsync(`DELETE FROM confirmed_local_results;`);
  }
}
