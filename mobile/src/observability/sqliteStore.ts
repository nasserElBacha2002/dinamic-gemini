import type { SQLiteDatabase } from '../database/database';
import type { ObservabilityEvent, ObservabilityReporter } from './types';

export interface ObservabilityEventRow {
  readonly id: string;
  readonly name: string;
  readonly timestamp: string;
  readonly session_id: string | null;
  readonly server_job_id: string | null;
  readonly client_file_id: string | null;
  readonly batch_id: string | null;
  readonly attempt_id: string | null;
  readonly duration_ms: number | null;
  readonly attributes_json: string;
  readonly created_at: string;
}

/**
 * SQLite-backed store for observability events (survives process death).
 * Failures are swallowed by SafeObservabilityReporter at the edge.
 */
export class SqliteObservabilityStore {
  constructor(private readonly db: SQLiteDatabase) {}

  async insert(event: ObservabilityEvent, id: string): Promise<void> {
    const createdAt = new Date().toISOString();
    await this.db.runAsync(
      `INSERT INTO observability_events (
        id, name, timestamp, session_id, server_job_id, client_file_id,
        batch_id, attempt_id, duration_ms, attributes_json, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
      id,
      event.name,
      event.timestamp,
      event.sessionId ?? null,
      event.serverJobId ?? null,
      event.clientFileId ?? null,
      event.batchId ?? null,
      event.attemptId ?? null,
      event.durationMs ?? null,
      JSON.stringify(event.attributes ?? {}),
      createdAt,
    );
  }

  async insertMany(rows: readonly { id: string; event: ObservabilityEvent }[]): Promise<void> {
    if (rows.length === 0) {
      return;
    }
    await this.db.execAsync('BEGIN;');
    try {
      for (const row of rows) {
        await this.insert(row.event, row.id);
      }
      await this.db.execAsync('COMMIT;');
    } catch (e) {
      await this.db.execAsync('ROLLBACK;');
      throw e;
    }
  }

  async listRecent(limit = 2000): Promise<ObservabilityEventRow[]> {
    return this.db.getAllAsync<ObservabilityEventRow>(
      `SELECT * FROM observability_events ORDER BY created_at DESC LIMIT ?;`,
      limit,
    );
  }

  async listBySession(sessionId: string, limit = 500): Promise<ObservabilityEventRow[]> {
    return this.db.getAllAsync<ObservabilityEventRow>(
      `SELECT * FROM observability_events
       WHERE session_id = ?
       ORDER BY created_at ASC
       LIMIT ?;`,
      sessionId,
      limit,
    );
  }

  async pruneOlderThan(isoTimestamp: string): Promise<number> {
    const result = await this.db.runAsync(
      `DELETE FROM observability_events WHERE created_at < ?;`,
      isoTimestamp,
    );
    return result.changes ?? 0;
  }

  async count(): Promise<number> {
    const row = await this.db.getFirstAsync<{ c: number }>(
      `SELECT COUNT(*) AS c FROM observability_events;`,
    );
    return row?.c ?? 0;
  }
}

/**
 * Buffers events and flushes asynchronously in batches so upload path is not blocked.
 */
export class BufferedSqliteObservabilityReporter implements ObservabilityReporter {
  private buffer: { id: string; event: ObservabilityEvent }[] = [];
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private flushing = false;

  constructor(
    private readonly store: SqliteObservabilityStore,
    private readonly options: {
      readonly createId: () => string;
      readonly flushSize?: number;
      readonly flushIntervalMs?: number;
      readonly onError?: (error: unknown) => void;
    },
  ) {}

  emit(event: ObservabilityEvent): void {
    this.buffer.push({ id: this.options.createId(), event });
    const flushSize = this.options.flushSize ?? 12;
    if (this.buffer.length >= flushSize) {
      void this.flush();
      return;
    }
    if (!this.flushTimer) {
      const interval = this.options.flushIntervalMs ?? 1500;
      this.flushTimer = setTimeout(() => {
        this.flushTimer = null;
        void this.flush();
      }, interval);
    }
  }

  async flush(): Promise<void> {
    if (this.flushing || this.buffer.length === 0) {
      return;
    }
    this.flushing = true;
    const batch = this.buffer.splice(0, this.buffer.length);
    try {
      await this.store.insertMany(batch);
    } catch (err) {
      this.options.onError?.(err);
    } finally {
      this.flushing = false;
    }
  }

  async dispose(): Promise<void> {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    await this.flush();
  }
}
