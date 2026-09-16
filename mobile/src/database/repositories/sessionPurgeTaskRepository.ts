/**
 * Durable session purge tasks — retain URIs until physical delete confirms.
 */

import type { SQLiteDatabase } from '../database';
import { withSqliteBusyRetry } from '../sqliteWriteGate';

export type SessionPurgeTaskState = 'PURGE_PENDING' | 'PURGE_PARTIAL' | 'PURGE_COMPLETE';

export interface SessionPurgeTaskRow {
  readonly capture_session_id: string;
  readonly state: SessionPurgeTaskState;
  readonly pending_uris_json: string;
  readonly last_error: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class SessionPurgeTaskRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async upsertPending(sessionId: string, pendingUris: readonly string[], lastError?: string | null): Promise<void> {
    const now = new Date().toISOString();
    const json = JSON.stringify([...new Set(pendingUris)]);
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `INSERT INTO session_purge_tasks (
           capture_session_id, state, pending_uris_json, last_error, created_at, updated_at
         ) VALUES (?, 'PURGE_PENDING', ?, ?, ?, ?)
         ON CONFLICT(capture_session_id) DO UPDATE SET
           state = 'PURGE_PENDING',
           pending_uris_json = excluded.pending_uris_json,
           last_error = excluded.last_error,
           updated_at = excluded.updated_at;`,
        sessionId,
        json,
        lastError ?? null,
        now,
        now,
      ),
    );
  }

  async markPartial(sessionId: string, pendingUris: readonly string[], lastError: string): Promise<void> {
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE session_purge_tasks SET
           state = 'PURGE_PARTIAL',
           pending_uris_json = ?,
           last_error = ?,
           updated_at = ?
         WHERE capture_session_id = ?;`,
        JSON.stringify([...new Set(pendingUris)]),
        lastError,
        now,
        sessionId,
      ),
    );
  }

  async markComplete(sessionId: string): Promise<void> {
    const now = new Date().toISOString();
    await withSqliteBusyRetry(() =>
      this.db.runAsync(
        `UPDATE session_purge_tasks SET
           state = 'PURGE_COMPLETE',
           pending_uris_json = '[]',
           last_error = NULL,
           updated_at = ?
         WHERE capture_session_id = ?;`,
        now,
        sessionId,
      ),
    );
  }

  async get(sessionId: string): Promise<SessionPurgeTaskRow | null> {
    return this.db.getFirstAsync<SessionPurgeTaskRow>(
      'SELECT * FROM session_purge_tasks WHERE capture_session_id = ? LIMIT 1;',
      sessionId,
    );
  }

  async listIncomplete(limit = 50): Promise<SessionPurgeTaskRow[]> {
    const rows = await this.db.getAllAsync<SessionPurgeTaskRow>(
      `SELECT * FROM session_purge_tasks
       WHERE state IN ('PURGE_PENDING','PURGE_PARTIAL')
       ORDER BY updated_at ASC
       LIMIT ?;`,
      limit,
    );
    return rows ?? [];
  }

  parsePendingUris(row: SessionPurgeTaskRow): string[] {
    try {
      const parsed = JSON.parse(row.pending_uris_json) as unknown;
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((u): u is string => typeof u === 'string' && u.length > 0);
    } catch {
      return [];
    }
  }
}
