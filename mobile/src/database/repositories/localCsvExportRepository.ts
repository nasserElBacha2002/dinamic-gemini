import type { SQLiteDatabase } from '../database';
import { withSqliteBusyRetry } from '../sqliteWriteGate';

export interface LocalCsvExportRow {
  readonly id: string;
  readonly export_id: string;
  readonly schema_version: string;
  readonly scope: string;
  readonly capture_session_id: string | null;
  readonly inventory_id: string;
  readonly aisle_id: string | null;
  readonly row_count: number;
  readonly checksum_sha256: string;
  readonly content_fingerprint: string;
  readonly file_uri: string | null;
  readonly exported_at: string;
  readonly shared_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class LocalCsvExportRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async findByFingerprint(fingerprint: string): Promise<LocalCsvExportRow | null> {
    return this.db.getFirstAsync<LocalCsvExportRow>(
      'SELECT * FROM local_csv_exports WHERE content_fingerprint = ? ORDER BY exported_at DESC LIMIT 1;',
      fingerprint,
    );
  }

  async findByExportId(exportId: string): Promise<LocalCsvExportRow | null> {
    return this.db.getFirstAsync<LocalCsvExportRow>(
      'SELECT * FROM local_csv_exports WHERE export_id = ? LIMIT 1;',
      exportId,
    );
  }

  async insert(row: LocalCsvExportRow): Promise<void> {
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `INSERT INTO local_csv_exports (
          id, export_id, schema_version, scope, capture_session_id, inventory_id, aisle_id,
          row_count, checksum_sha256, content_fingerprint, file_uri, exported_at, shared_at,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
        row.id,
        row.export_id,
        row.schema_version,
        row.scope,
        row.capture_session_id,
        row.inventory_id,
        row.aisle_id,
        row.row_count,
        row.checksum_sha256,
        row.content_fingerprint,
        row.file_uri,
        row.exported_at,
        row.shared_at,
        row.created_at,
        row.updated_at,
      ),
    );
  }

  async markShared(exportId: string, sharedAt: string): Promise<void> {
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        'UPDATE local_csv_exports SET shared_at = ?, updated_at = ? WHERE export_id = ?;',
        sharedAt,
        sharedAt,
        exportId,
      ),
    );
  }

  async listForSession(sessionId: string): Promise<LocalCsvExportRow[]> {
    return this.db.getAllAsync<LocalCsvExportRow>(
      'SELECT * FROM local_csv_exports WHERE capture_session_id = ? ORDER BY exported_at DESC;',
      sessionId,
    );
  }
}
