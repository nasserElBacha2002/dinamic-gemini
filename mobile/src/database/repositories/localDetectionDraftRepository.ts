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
  | 'FAILED';

export interface LocalDetectionDraftRow {
  readonly id: string;
  readonly capture_photo_id: string;
  readonly capture_session_id: string;
  readonly client_file_id: string | null;
  readonly status: LocalDetectionDraftStatus;
  readonly raw_value_hash: string | null;
  readonly raw_value_preview: string | null;
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
  readonly compare_result: string | null;
  readonly compared_at: string | null;
  readonly prepared_asset_fingerprint: string | null;
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
    readonly rawValuePreview?: string | null;
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
  }): Promise<LocalDetectionDraftRow> {
    const now = new Date().toISOString();
    const existing = await this.getByIdempotencyKey(
      input.capturePhotoId,
      input.detectorVersion,
      input.parserVersion,
      input.preparedAssetFingerprint,
    );
    const id = existing?.id ?? createId();
    await this.db.runAsync(
      `INSERT INTO local_detection_drafts (
        id, capture_photo_id, capture_session_id, client_file_id, status,
        raw_value_hash, raw_value_preview, internal_code, quantity, quantity_status,
        detected_format, detected_symbology, parser_version, detector_version,
        candidate_count, error_code, processing_ms, compare_result, compared_at,
        prepared_asset_fingerprint, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
      ON CONFLICT(capture_photo_id, detector_version, parser_version, prepared_asset_fingerprint)
      DO UPDATE SET
        status = excluded.status,
        client_file_id = excluded.client_file_id,
        raw_value_hash = excluded.raw_value_hash,
        raw_value_preview = excluded.raw_value_preview,
        internal_code = excluded.internal_code,
        quantity = excluded.quantity,
        quantity_status = excluded.quantity_status,
        detected_format = excluded.detected_format,
        detected_symbology = excluded.detected_symbology,
        candidate_count = excluded.candidate_count,
        error_code = excluded.error_code,
        processing_ms = excluded.processing_ms,
        updated_at = excluded.updated_at;`,
      id,
      input.capturePhotoId,
      input.captureSessionId,
      input.clientFileId,
      input.status,
      input.rawValueHash ?? null,
      input.rawValuePreview ?? null,
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
      input.preparedAssetFingerprint,
      existing?.created_at ?? now,
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

  async markCompared(id: string, compareResult: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `UPDATE local_detection_drafts
       SET compare_result = ?, compared_at = ?, updated_at = ?
       WHERE id = ?;`,
      compareResult,
      now,
      now,
      id,
    );
  }
}
