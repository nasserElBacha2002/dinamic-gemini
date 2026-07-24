import type { SQLiteDatabase } from 'expo-sqlite';

export type ServerReprocessIntentStatus =
  | 'REPROCESS_REQUEST_PENDING'
  | 'SYNCING'
  | 'COMPLETED'
  | 'RETRY_SCHEDULED'
  | 'FAILED_TERMINAL'
  | 'CONFLICT';

export interface ServerReprocessRequestIntent {
  readonly id: string;
  readonly request_id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly scope_type: string;
  readonly scope_json: string;
  readonly processing_mode: string;
  readonly reason: string;
  readonly status: ServerReprocessIntentStatus;
  readonly last_error_code: string | null;
  readonly attempt_count: number;
  readonly next_retry_at: string | null;
  readonly server_run_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class ServerReprocessIntentRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async upsertPending(input: {
    readonly id: string;
    readonly requestId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly scopeType: string;
    readonly scopeJson: string;
    readonly processingMode: string;
    readonly reason: string;
    readonly nowIso: string;
  }): Promise<void> {
    const existing = await this.db.getFirstAsync<{ request_id: string }>(
      `SELECT request_id FROM server_reprocess_request_intents WHERE request_id = ? LIMIT 1;`,
      input.requestId,
    );
    if (existing) {
      await this.db.runAsync(
        `UPDATE server_reprocess_request_intents
         SET status = 'REPROCESS_REQUEST_PENDING', last_error_code = NULL, updated_at = ?
         WHERE request_id = ?;`,
        input.nowIso,
        input.requestId,
      );
      return;
    }
    await this.db.runAsync(
      `INSERT INTO server_reprocess_request_intents (
         id, request_id, inventory_id, aisle_id, scope_type, scope_json,
         processing_mode, reason, status, last_error_code, attempt_count,
         next_retry_at, server_run_id, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'REPROCESS_REQUEST_PENDING', NULL, 0, NULL, NULL, ?, ?);`,
      input.id,
      input.requestId,
      input.inventoryId,
      input.aisleId,
      input.scopeType,
      input.scopeJson,
      input.processingMode,
      input.reason,
      input.nowIso,
      input.nowIso,
    );
  }

  async markCompleted(requestId: string, serverRunId: string, nowIso: string): Promise<void> {
    await this.db.runAsync(
      `UPDATE server_reprocess_request_intents
       SET status = 'COMPLETED', server_run_id = ?, updated_at = ?
       WHERE request_id = ?;`,
      serverRunId,
      nowIso,
      requestId,
    );
  }

  async listPending(limit = 20): Promise<ServerReprocessRequestIntent[]> {
    const rows = await this.db.getAllAsync<ServerReprocessRequestIntent>(
      `SELECT * FROM server_reprocess_request_intents
       WHERE status IN ('REPROCESS_REQUEST_PENDING', 'RETRY_SCHEDULED')
       ORDER BY created_at ASC
       LIMIT ?;`,
      limit,
    );
    return rows ?? [];
  }
}
