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
  readonly checksum_algorithm?: string;
  readonly content_fingerprint: string;
  readonly file_uri: string | null;
  /** Durable ZIP path (v38+). Historical rows may be null — use resolveZipUri. */
  readonly zip_uri?: string | null;
  readonly freeze_id?: string | null;
  readonly zip_size_bytes?: number | null;
  readonly zip_sha256?: string | null;
  readonly package_checksum_sha256?: string | null;
  readonly exported_at: string;
  readonly shared_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/**
 * Deterministic historical backfill: versioned `exportId.token.csv` → `.zip`.
 * Returns null when pattern is not a safe same-basename pair.
 */
export function deriveZipUriFromCsvUri(fileUri: string | null | undefined): string | null {
  if (!fileUri) return null;
  if (!/\.csv$/i.test(fileUri)) return null;
  if (!fileUri.includes('/aisle-exports/')) return null;
  return fileUri.replace(/\.csv$/i, '.zip');
}

export function resolveZipUri(row: Pick<LocalCsvExportRow, 'file_uri' | 'zip_uri'>): string | null {
  if (row.zip_uri) return row.zip_uri;
  return deriveZipUriFromCsvUri(row.file_uri);
}

export class LocalCsvExportRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async findByFingerprint(fingerprint: string): Promise<LocalCsvExportRow | null> {
    return this.db.getFirstAsync<LocalCsvExportRow>(
      'SELECT * FROM local_csv_exports WHERE content_fingerprint = ? ORDER BY exported_at DESC LIMIT 1;',
      fingerprint,
    );
  }

  async findBySessionAndFingerprint(
    sessionId: string,
    fingerprint: string,
  ): Promise<LocalCsvExportRow | null> {
    return this.db.getFirstAsync<LocalCsvExportRow>(
      `SELECT * FROM local_csv_exports
       WHERE capture_session_id = ? AND content_fingerprint = ?
       ORDER BY exported_at DESC LIMIT 1;`,
      sessionId,
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
    const zipUri = row.zip_uri ?? deriveZipUriFromCsvUri(row.file_uri);
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `INSERT INTO local_csv_exports (
          id, export_id, schema_version, scope, capture_session_id, inventory_id, aisle_id,
          row_count, checksum_sha256, content_fingerprint, file_uri, exported_at, shared_at,
          created_at, updated_at, freeze_id, checksum_algorithm,
          zip_size_bytes, zip_sha256, package_checksum_sha256, zip_uri
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
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
        row.freeze_id ?? null,
        row.checksum_algorithm ?? 'sha256',
        row.zip_size_bytes ?? null,
        row.zip_sha256 ?? null,
        row.package_checksum_sha256 ?? null,
        zipUri,
      ),
    );
  }

  /**
   * Idempotent insert for concurrent exporters of the same session+fingerprint.
   * Returns true when this caller inserted the row; false when a peer won the race.
   */
  async tryInsert(row: LocalCsvExportRow): Promise<boolean> {
    try {
      await this.insert(row);
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (
        message.toLowerCase().includes('unique') ||
        message.toLowerCase().includes('constraint')
      ) {
        return false;
      }
      throw error;
    }
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

  async findByFileUri(fileUri: string): Promise<LocalCsvExportRow | null> {
    return this.db.getFirstAsync<LocalCsvExportRow>(
      'SELECT * FROM local_csv_exports WHERE file_uri = ? LIMIT 1;',
      fileUri,
    );
  }

  async findByZipUri(zipUri: string): Promise<LocalCsvExportRow | null> {
    const byCol = await this.db.getFirstAsync<LocalCsvExportRow>(
      'SELECT * FROM local_csv_exports WHERE zip_uri = ? LIMIT 1;',
      zipUri,
    );
    if (byCol) return byCol;
    // Historical rows: derive from file_uri (same versioned basename).
    if (!/\.zip$/i.test(zipUri) || !zipUri.includes('/aisle-exports/')) return null;
    const csvCandidate = zipUri.replace(/\.zip$/i, '.csv');
    const byCsv = await this.findByFileUri(csvCandidate);
    if (!byCsv) return null;
    const derived = deriveZipUriFromCsvUri(byCsv.file_uri);
    return derived === zipUri ? byCsv : null;
  }

  /**
   * Authoritative reference check — no LIMIT as absence proof.
   * Matches file_uri, zip_uri, or deterministic historical CSV↔ZIP pair.
   */
  async isArtifactReferenced(uri: string): Promise<boolean> {
    const direct = await this.db.getFirstAsync<{ id: string }>(
      `SELECT id FROM local_csv_exports
       WHERE file_uri = ? OR zip_uri = ?
       LIMIT 1;`,
      uri,
      uri,
    );
    if (direct) return true;
    if (/\.zip$/i.test(uri) && uri.includes('/aisle-exports/')) {
      const hist = await this.findByZipUri(uri);
      return Boolean(hist);
    }
    if (/\.csv$/i.test(uri) && uri.includes('/aisle-exports/')) {
      const hist = await this.findByFileUri(uri);
      return Boolean(hist);
    }
    return false;
  }

  async deleteForSession(sessionId: string): Promise<number> {
    const result = await withSqliteBusyRetry(() =>
      this.db.runAsync('DELETE FROM local_csv_exports WHERE capture_session_id = ?;', sessionId),
    );
    return result.changes ?? 0;
  }

  /** Delete one export row only after its files are confirmed gone. */
  async deleteById(id: string): Promise<number> {
    const result = await withSqliteBusyRetry(() =>
      this.db.runAsync('DELETE FROM local_csv_exports WHERE id = ?;', id),
    );
    return result.changes ?? 0;
  }
}
