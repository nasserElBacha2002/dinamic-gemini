import type { CompositeCursor } from '../../core/compositeCursor';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus, CaptureSessionStatus } from '../../domain/enums/photoStatus';

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
  readonly created_at: string;
  readonly updated_at: string;
}

export function cursorFromSession(row: CaptureSessionRow, kind: 'scan' | 'lastValid'): CompositeCursor {
  return kind === 'scan'
    ? { dateAdded: row.scan_cursor_date_added, assetId: row.scan_cursor_asset_id }
    : { dateAdded: row.last_valid_cursor_date_added, assetId: row.last_valid_cursor_asset_id };
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

