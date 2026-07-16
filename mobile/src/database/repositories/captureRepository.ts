import type { CompositeCursor } from '../../core/compositeCursor';
import { EMPTY_CURSOR } from '../../core/compositeCursor';
import {
  OPEN_CAPTURE_SESSION_STATUSES,
  canTransitionPhoto,
  canTransitionSession,
} from '../../core/captureState';
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
    await this.db.execAsync('BEGIN IMMEDIATE;');
    try {
      const existing = await this.findCurrentOpenSession();
      if (existing) {
        await this.db.execAsync('COMMIT;');
        return { session: existing, created: false };
      }
      const session = await this.insertSession(input, 'preparing');
      await this.db.execAsync('COMMIT;');
      return { session, created: true };
    } catch (e) {
      await this.db.execAsync('ROLLBACK;');
      throw e;
    }
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
        last_valid_cursor_date_added, last_valid_cursor_asset_id, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
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
    const placeholders = OPEN_CAPTURE_SESSION_STATUSES.map(() => '?').join(', ');
    return this.db.getAllAsync<CaptureSessionRow>(
      `SELECT * FROM capture_sessions WHERE status IN (${placeholders}) ORDER BY updated_at DESC;`,
      ...OPEN_CAPTURE_SESSION_STATUSES,
    );
  }

  async findCurrentOpenSession(): Promise<CaptureSessionRow | null> {
    const [session] = await this.listOpenSessions();
    return session ?? null;
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
  }

  async repairMultipleOpenSessions(keepSessionId: string, reason: string): Promise<void> {
    const now = new Date().toISOString();
    const placeholders = OPEN_CAPTURE_SESSION_STATUSES.map(() => '?').join(', ');
    await this.db.runAsync(
      `UPDATE capture_sessions
       SET status = 'failed', updated_at = ?
       WHERE id <> ? AND status IN (${placeholders});`,
      now,
      keepSessionId,
      ...OPEN_CAPTURE_SESSION_STATUSES,
    );
    // Keep reason in logs/documentation for now; session table has no failure_reason column in v1.
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
        status = CASE WHEN capture_photos.status = 'excluded' THEN capture_photos.status ELSE excluded.status END,
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
    const current = await this.getPhoto(sessionId, assetId);
    if (!current) {
      throw new Error(`Capture photo not found: ${assetId}`);
    }
    if (!canTransitionPhoto(current.status, status)) {
      throw new Error(`Invalid capture photo transition: ${current.status} -> ${status}`);
    }
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

  async applyStabilityResult(input: StabilityResultInput): Promise<boolean> {
    const current = await this.getPhoto(input.sessionId, input.assetId);
    if (!current) {
      return false;
    }
    if (!canTransitionPhoto(current.status, input.status)) {
      return false;
    }
    const now = new Date().toISOString();
    const result = await this.db.runAsync(
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

