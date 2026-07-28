import { type CompositeCursor, EMPTY_CURSOR } from '../../core/compositeCursor';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus, CaptureSessionStatus } from '../../domain/enums/photoStatus';
import type { PhotoUploadStatus, UploadBatchStatus, ProcessingJobLocalStatus } from '../../domain/enums/uploadStatus';

export interface CaptureSessionRow {
  readonly id: string;
  readonly inventory_id: string;
  readonly inventory_name: string;
  readonly aisle_id: string;
  readonly aisle_name: string;
  readonly status: CaptureSessionStatus;
  readonly started_at: string;
  readonly finished_at: string | null;
  readonly initial_asset_id: string | null;
  readonly initial_date_added: number | null;
  readonly initial_date_modified: number | null;
  readonly initial_display_name: string | null;
  readonly initial_size: number | null;
  readonly initial_bucket_id: number | null;
  readonly scan_cursor_date_added: number;
  readonly scan_cursor_asset_id: string;
  readonly last_valid_cursor_date_added: number;
  readonly last_valid_cursor_asset_id: string;
  readonly upload_batch_id: string | null;
  readonly upload_status: string;
  readonly processing_status: string;
  readonly backend_job_id: string | null;
  readonly upload_started_at: string | null;
  readonly upload_completed_at: string | null;
  readonly processing_started_at: string | null;
  readonly processing_finished_at: string | null;
  readonly last_upload_error: string | null;
  readonly last_processing_error: string | null;
  /** Preparation profile hint: CODE_SCAN | INTERNAL_OCR | LEGACY_LLM | UNKNOWN */
  readonly preparation_processing_mode: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CapturePhotoRow {
  readonly id: string;
  readonly capture_session_id: string;
  readonly asset_id: string;
  readonly media_store_numeric_id: number | null;
  readonly uri: string;
  readonly display_name: string;
  readonly mime_type: string;
  readonly size: number;
  readonly width: number;
  readonly height: number;
  readonly date_added: number;
  readonly date_modified: number;
  readonly bucket_id: number | null;
  readonly relative_path: string | null;
  readonly status: CapturePhotoStatus;
  readonly rejection_reason: string | null;
  readonly stability_checks: number;
  readonly stability_attempts: number;
  readonly stability_error: string | null;
  readonly last_stability_attempt_at: string | null;
  readonly detected_at: string | null;
  readonly stable_at: string | null;
  readonly excluded_at: string | null;
  readonly client_file_id: string | null;
  readonly backend_asset_id: string | null;
  readonly upload_status: PhotoUploadStatus;
  readonly upload_progress: number;
  readonly upload_attempts: number;
  readonly upload_batch_id: string | null;
  readonly last_upload_error_code: string | null;
  readonly last_upload_error_message: string | null;
  readonly last_upload_attempt_at: string | null;
  readonly next_retry_at: string | null;
  readonly uploaded_at: string | null;
  readonly remote_deleted_at: string | null;
  readonly local_transform_uri: string | null;
  readonly original_size: number | null;
  readonly upload_size: number | null;
  /** Phase 2: `js` | `native` while a lease is held. */
  readonly upload_worker_owner: string | null;
  readonly upload_lease_token: string | null;
  readonly upload_lease_expires_at: string | null;
  readonly upload_heartbeat_at: string | null;
  /** 1 when cancel was requested while uploading (settlement still pending). */
  readonly upload_cancel_requested: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface UploadBatchRow {
  readonly id: string;
  readonly capture_session_id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly status: UploadBatchStatus;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly attempt_count: number;
  readonly last_error: string | null;
}

export interface ProcessingJobRow {
  readonly id: string;
  readonly capture_session_id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly backend_job_id: string;
  readonly status: ProcessingJobLocalStatus;
  readonly remote_status: string | null;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly finished_at: string | null;
  readonly last_polled_at: string | null;
  readonly next_poll_at: string | null;
  readonly attempt_count: number;
  readonly error_code: string | null;
  readonly error_message: string | null;
}

export function cursorFromSession(row: CaptureSessionRow, kind: 'scan' | 'lastValid'): CompositeCursor {
  return kind === 'scan'
    ? { dateAdded: row.scan_cursor_date_added, assetId: row.scan_cursor_asset_id }
    : { dateAdded: row.last_valid_cursor_date_added, assetId: row.last_valid_cursor_asset_id };
}

/**
 * Fixed lower bound for a session: the newest photo that existed when capture started.
 * Every photo added afterwards is strictly after this cursor. Unlike the scan cursor,
 * this NEVER advances, so batch downloads that share a DATE_ADDED second (or index out of
 * assetId order) stay discoverable on later scans instead of being permanently skipped.
 */
export function cursorFromInitialMarker(row: CaptureSessionRow): CompositeCursor {
  if (row.initial_asset_id === null || row.initial_date_added === null) {
    return EMPTY_CURSOR;
  }
  return { dateAdded: row.initial_date_added, assetId: row.initial_asset_id };
}

export function imageFromPhotoRow(row: CapturePhotoRow): GalleryImage {
  return {
    assetId: row.asset_id,
    ...(row.media_store_numeric_id !== null ? { mediaStoreNumericId: row.media_store_numeric_id } : {}),
    uri: row.uri,
    displayName: row.display_name,
    mimeType: row.mime_type,
    size: row.size,
    width: row.width,
    height: row.height,
    dateAdded: row.date_added,
    dateModified: row.date_modified,
    bucketId: row.bucket_id,
    relativePath: row.relative_path,
  };
}
