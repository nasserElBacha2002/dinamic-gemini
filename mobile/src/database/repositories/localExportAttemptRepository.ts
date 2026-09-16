import type { SQLiteDatabase } from '../database';
import { withSqliteBusyRetry } from '../sqliteWriteGate';
import type { ExportAttemptState } from '../../features/exportPrep/artifactRetentionPolicy';
import { isActiveExportAttemptState } from '../../features/exportPrep/artifactRetentionPolicy';

export interface LocalExportAttemptRow {
  readonly id: string;
  readonly capture_session_id: string;
  readonly freeze_id: string | null;
  readonly freeze_generation: number | null;
  readonly content_fingerprint: string | null;
  readonly state: ExportAttemptState;
  readonly tmp_csv_uri: string | null;
  readonly tmp_zip_uri: string | null;
  readonly final_csv_uri: string | null;
  readonly final_zip_uri: string | null;
  readonly started_at: string;
  readonly heartbeat_at: string;
  readonly completed_at: string | null;
  readonly error_code: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class ExportAttemptTransitionError extends Error {
  constructor(
    readonly attemptId: string,
    readonly fromExpected: readonly ExportAttemptState[],
    readonly to: ExportAttemptState,
  ) {
    super(
      `EXPORT_ATTEMPT_TRANSITION_REJECTED: ${attemptId} -> ${to} (expected one of ${fromExpected.join(',')})`,
    );
    this.name = 'ExportAttemptTransitionError';
  }
}

/** Allowed predecessors for each target state (CAS). Terminal states have no outgoing edges. */
export const EXPORT_ATTEMPT_TRANSITIONS: Readonly<
  Record<ExportAttemptState, readonly ExportAttemptState[]>
> = {
  CREATED: [],
  WRITING: ['CREATED'],
  VALIDATING: ['WRITING'],
  PUBLISHING: ['VALIDATING'],
  COMPLETE: ['PUBLISHING'],
  FAILED: ['CREATED', 'WRITING', 'VALIDATING', 'PUBLISHING'],
  CANCELLED: ['CREATED', 'WRITING', 'VALIDATING', 'PUBLISHING'],
};

export type AttemptStatePatch = {
  readonly tmp_csv_uri?: string | null;
  readonly tmp_zip_uri?: string | null;
  readonly final_csv_uri?: string | null;
  readonly final_zip_uri?: string | null;
  readonly error_code?: string | null;
  readonly completed_at?: string | null;
  readonly content_fingerprint?: string | null;
};

export class LocalExportAttemptRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async insert(row: LocalExportAttemptRow): Promise<void> {
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `INSERT INTO local_export_attempts (
          id, capture_session_id, freeze_id, freeze_generation, content_fingerprint, state,
          tmp_csv_uri, tmp_zip_uri, final_csv_uri, final_zip_uri,
          started_at, heartbeat_at, completed_at, error_code, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
        row.id,
        row.capture_session_id,
        row.freeze_id,
        row.freeze_generation,
        row.content_fingerprint,
        row.state,
        row.tmp_csv_uri,
        row.tmp_zip_uri,
        row.final_csv_uri,
        row.final_zip_uri,
        row.started_at,
        row.heartbeat_at,
        row.completed_at,
        row.error_code,
        row.created_at,
        row.updated_at,
      ),
    );
  }

  async getById(id: string): Promise<LocalExportAttemptRow | null> {
    return this.db.getFirstAsync<LocalExportAttemptRow>(
      'SELECT * FROM local_export_attempts WHERE id = ? LIMIT 1;',
      id,
    );
  }

  async listActiveForSession(sessionId: string): Promise<LocalExportAttemptRow[]> {
    const rows = await this.db.getAllAsync<LocalExportAttemptRow>(
      `SELECT * FROM local_export_attempts
       WHERE capture_session_id = ?
         AND state IN ('CREATED','WRITING','VALIDATING','PUBLISHING')
       ORDER BY started_at ASC;`,
      sessionId,
    );
    return rows ?? [];
  }

  async listActiveGlobal(limit = 50): Promise<LocalExportAttemptRow[]> {
    const rows = await this.db.getAllAsync<LocalExportAttemptRow>(
      `SELECT * FROM local_export_attempts
       WHERE state IN ('CREATED','WRITING','VALIDATING','PUBLISHING')
       ORDER BY heartbeat_at ASC
       LIMIT ?;`,
      limit,
    );
    return rows ?? [];
  }

  async listPublishing(limit = 50): Promise<LocalExportAttemptRow[]> {
    const rows = await this.db.getAllAsync<LocalExportAttemptRow>(
      `SELECT * FROM local_export_attempts
       WHERE state = 'PUBLISHING'
       ORDER BY heartbeat_at ASC
       LIMIT ?;`,
      limit,
    );
    return rows ?? [];
  }

  async listBySession(sessionId: string): Promise<LocalExportAttemptRow[]> {
    const rows = await this.db.getAllAsync<LocalExportAttemptRow>(
      `SELECT * FROM local_export_attempts WHERE capture_session_id = ? ORDER BY started_at DESC;`,
      sessionId,
    );
    return rows ?? [];
  }

  async heartbeat(id: string, atIso: string): Promise<boolean> {
    const result = await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE local_export_attempts SET heartbeat_at = ?, updated_at = ?
         WHERE id = ? AND state IN ('CREATED','WRITING','VALIDATING','PUBLISHING');`,
        atIso,
        atIso,
        id,
      ),
    );
    return (result.changes ?? 0) === 1;
  }

  /**
   * Atomic compare-and-set transition. Rejected transitions throw — never silent no-op.
   */
  async transitionState(
    id: string,
    to: ExportAttemptState,
    patch?: AttemptStatePatch,
    fromOverride?: readonly ExportAttemptState[],
  ): Promise<LocalExportAttemptRow> {
    const fromAllowed = fromOverride ?? EXPORT_ATTEMPT_TRANSITIONS[to];
    if (fromAllowed.length === 0) {
      throw new ExportAttemptTransitionError(id, fromAllowed, to);
    }
    const now = new Date().toISOString();
    const existing = await this.getById(id);
    if (!existing) {
      throw new ExportAttemptTransitionError(id, fromAllowed, to);
    }

    const placeholders = fromAllowed.map(() => '?').join(',');
    const result = await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE local_export_attempts SET
          state = ?,
          tmp_csv_uri = COALESCE(?, tmp_csv_uri),
          tmp_zip_uri = COALESCE(?, tmp_zip_uri),
          final_csv_uri = COALESCE(?, final_csv_uri),
          final_zip_uri = COALESCE(?, final_zip_uri),
          error_code = COALESCE(?, error_code),
          completed_at = COALESCE(?, completed_at),
          content_fingerprint = COALESCE(?, content_fingerprint),
          heartbeat_at = ?,
          updated_at = ?
         WHERE id = ? AND state IN (${placeholders});`,
        to,
        patch?.tmp_csv_uri !== undefined ? patch.tmp_csv_uri : null,
        patch?.tmp_zip_uri !== undefined ? patch.tmp_zip_uri : null,
        patch?.final_csv_uri !== undefined ? patch.final_csv_uri : null,
        patch?.final_zip_uri !== undefined ? patch.final_zip_uri : null,
        patch?.error_code !== undefined ? patch.error_code : null,
        patch?.completed_at !== undefined ? patch.completed_at : null,
        patch?.content_fingerprint !== undefined ? patch.content_fingerprint : null,
        now,
        now,
        id,
        ...fromAllowed,
      ),
    );

    if ((result.changes ?? 0) !== 1) {
      throw new ExportAttemptTransitionError(id, fromAllowed, to);
    }
    const updated = await this.getById(id);
    if (!updated) {
      throw new ExportAttemptTransitionError(id, fromAllowed, to);
    }
    return updated;
  }

  /**
   * @deprecated Use transitionState — kept temporarily for call-site migration.
   * Always CAS; throws on rejected transition.
   */
  async updateState(
    id: string,
    state: ExportAttemptState,
    patch?: AttemptStatePatch,
  ): Promise<void> {
    await this.transitionState(id, state, patch);
  }

  async deleteForSession(sessionId: string): Promise<number> {
    const result = await withSqliteBusyRetry(() =>
      this.db.runAsync(`DELETE FROM local_export_attempts WHERE capture_session_id = ?;`, sessionId),
    );
    return result.changes ?? 0;
  }

  /**
   * Mark active attempts with stale heartbeat as FAILED (bootstrap recovery).
   * CAS per row — skips already-terminal attempts.
   */
  async failStaleActive(maxAgeMs: number, nowMs = Date.now()): Promise<number> {
    const rows = await this.listActiveGlobal(200);
    let failed = 0;
    const cutoff = nowMs - maxAgeMs;
    for (const row of rows) {
      if (!isActiveExportAttemptState(row.state)) continue;
      const hb = Date.parse(row.heartbeat_at);
      if (!Number.isFinite(hb) || hb > cutoff) continue;
      try {
        await this.transitionState(row.id, 'FAILED', {
          error_code: 'EXPORT_ATTEMPT_STALE',
          completed_at: new Date(nowMs).toISOString(),
        });
        failed += 1;
      } catch {
        // lost race to cancel/complete — ok
      }
    }
    return failed;
  }

  /** Authoritative: is this URI owned by any COMPLETE attempt? (no LIMIT). */
  async isFinalUriReferencedByCompleteAttempt(uri: string): Promise<boolean> {
    const row = await this.db.getFirstAsync<{ id: string }>(
      `SELECT id FROM local_export_attempts
       WHERE state = 'COMPLETE'
         AND (final_csv_uri = ? OR final_zip_uri = ?)
       LIMIT 1;`,
      uri,
      uri,
    );
    return Boolean(row);
  }
}
