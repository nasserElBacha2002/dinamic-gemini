import type { CompositeCursor } from '../../core/compositeCursor';
import { EMPTY_CURSOR } from '../../core/compositeCursor';
import type { CaptureMarker } from '../../domain/entities/captureMarker';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus, CaptureSessionStatus } from '../../domain/enums/photoStatus';
import type { SQLiteDatabase } from '../database';
import type { CapturePhotoRow, CaptureSessionRow } from '../schema/captureSchema';

export interface CreateCaptureSessionInput {
  readonly id: string;
  readonly inventoryId: string;
  readonly inventoryName: string;
  readonly aisleId: string;
  readonly aisleName: string;
  readonly marker: CaptureMarker;
}

export class CaptureRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async createSession(input: CreateCaptureSessionInput): Promise<CaptureSessionRow> {
    const now = new Date().toISOString();
    const cursor = input.marker.assetId && input.marker.dateAdded !== null
      ? { dateAdded: input.marker.dateAdded, assetId: input.marker.assetId }
      : EMPTY_CURSOR;
    await this.db.runAsync(
      `INSERT INTO capture_sessions (
        id, inventory_id, inventory_name, aisle_id, aisle_name, status, started_at, finished_at,
        initial_asset_id, initial_date_added, initial_date_modified, initial_display_name,
        initial_size, initial_bucket_id, scan_cursor_date_added, scan_cursor_asset_id,
        last_valid_cursor_date_added, last_valid_cursor_asset_id, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
      input.id,
      input.inventoryId,
      input.inventoryName,
      input.aisleId,
      input.aisleName,
      'active',
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

  async listOpenSessions(): Promise<CaptureSessionRow[]> {
    return this.db.getAllAsync<CaptureSessionRow>(
      "SELECT * FROM capture_sessions WHERE status IN ('active', 'paused', 'finishing', 'review', 'failed') ORDER BY updated_at DESC;",
    );
  }

  async findOpenSessionForAisle(inventoryId: string, aisleId: string): Promise<CaptureSessionRow | null> {
    return this.db.getFirstAsync<CaptureSessionRow>(
      "SELECT * FROM capture_sessions WHERE inventory_id = ? AND aisle_id = ? AND status IN ('active', 'paused', 'finishing', 'review', 'failed') ORDER BY updated_at DESC LIMIT 1;",
      inventoryId,
      aisleId,
    );
  }

  async updateSessionStatus(id: string, status: CaptureSessionStatus, finished = false): Promise<void> {
    await this.db.runAsync(
      'UPDATE capture_sessions SET status = ?, finished_at = COALESCE(?, finished_at), updated_at = ? WHERE id = ?;',
      status,
      finished ? new Date().toISOString() : null,
      new Date().toISOString(),
      id,
    );
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

  async upsertPhoto(sessionId: string, image: GalleryImage, status: CapturePhotoStatus, rejectionReason: string | null = null): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `INSERT INTO capture_photos (
        id, capture_session_id, asset_id, media_store_numeric_id, uri, display_name, mime_type,
        size, width, height, date_added, date_modified, bucket_id, relative_path, status,
        rejection_reason, stability_checks, stability_error, detected_at, stable_at, excluded_at,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(capture_session_id, asset_id) DO UPDATE SET
        uri = excluded.uri,
        display_name = excluded.display_name,
        mime_type = excluded.mime_type,
        size = excluded.size,
        width = excluded.width,
        height = excluded.height,
        date_modified = excluded.date_modified,
        status = excluded.status,
        rejection_reason = excluded.rejection_reason,
        stable_at = CASE WHEN excluded.status = 'stable' THEN excluded.updated_at ELSE capture_photos.stable_at END,
        excluded_at = CASE WHEN excluded.status = 'excluded' THEN excluded.updated_at ELSE capture_photos.excluded_at END,
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
      now,
      now,
    );
  }

  async updatePhotoStatus(sessionId: string, assetId: string, status: CapturePhotoStatus, error: string | null = null): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
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
    );
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

