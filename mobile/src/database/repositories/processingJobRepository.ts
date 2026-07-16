import type { ProcessingJobLocalStatus } from '../../domain/enums/uploadStatus';
import type { SQLiteDatabase } from '../database';
import type { ProcessingJobRow } from '../schema/captureSchema';
import { createId } from '../../shared/createId';

export class ProcessingJobRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async create(input: {
    readonly captureSessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly backendJobId: string;
    readonly status: ProcessingJobLocalStatus;
    readonly remoteStatus?: string | null;
  }): Promise<ProcessingJobRow> {
    const id = createId();
    const now = new Date().toISOString();
    await this.db.runAsync(
      `INSERT INTO processing_jobs (
        id, capture_session_id, inventory_id, aisle_id, backend_job_id, status, remote_status,
        created_at, started_at, finished_at, last_polled_at, next_poll_at, attempt_count, error_code, error_message
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 0, NULL, NULL);`,
      id,
      input.captureSessionId,
      input.inventoryId,
      input.aisleId,
      input.backendJobId,
      input.status,
      input.remoteStatus ?? null,
      now,
      now,
      now,
    );
    const row = await this.getById(id);
    if (!row) {
      throw new Error('Failed to create processing job');
    }
    return row;
  }

  async getById(id: string): Promise<ProcessingJobRow | null> {
    return this.db.getFirstAsync<ProcessingJobRow>('SELECT * FROM processing_jobs WHERE id = ?;', id);
  }

  async getByBackendJobId(backendJobId: string): Promise<ProcessingJobRow | null> {
    return this.db.getFirstAsync<ProcessingJobRow>(
      'SELECT * FROM processing_jobs WHERE backend_job_id = ? ORDER BY created_at DESC LIMIT 1;',
      backendJobId,
    );
  }

  async listNonTerminal(): Promise<ProcessingJobRow[]> {
    return this.db.getAllAsync<ProcessingJobRow>(
      `SELECT * FROM processing_jobs
       WHERE status IN ('pending', 'running', 'unknown')
       ORDER BY created_at DESC;`,
    );
  }

  async listForSession(sessionId: string): Promise<ProcessingJobRow[]> {
    return this.db.getAllAsync<ProcessingJobRow>(
      'SELECT * FROM processing_jobs WHERE capture_session_id = ? ORDER BY created_at DESC;',
      sessionId,
    );
  }

  async updatePoll(input: {
    readonly id: string;
    readonly status: ProcessingJobLocalStatus;
    readonly remoteStatus: string;
    readonly nextPollAt: string | null;
    readonly errorCode?: string | null;
    readonly errorMessage?: string | null;
    readonly finished?: boolean;
  }): Promise<void> {
    const now = new Date().toISOString();
    await this.db.runAsync(
      `UPDATE processing_jobs SET
        status = ?,
        remote_status = ?,
        last_polled_at = ?,
        next_poll_at = ?,
        attempt_count = attempt_count + 1,
        error_code = COALESCE(?, error_code),
        error_message = COALESCE(?, error_message),
        finished_at = CASE WHEN ? THEN ? ELSE finished_at END
       WHERE id = ?;`,
      input.status,
      input.remoteStatus,
      now,
      input.nextPollAt,
      input.errorCode ?? null,
      input.errorMessage ?? null,
      input.finished ? 1 : 0,
      now,
      input.id,
    );
  }
}
