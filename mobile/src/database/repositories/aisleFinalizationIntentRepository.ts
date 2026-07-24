import type { SQLiteDatabase } from 'expo-sqlite';

export type FinalizationIntentStatus =
  | 'FINALIZATION_PENDING'
  | 'FINALIZATION_SYNCING'
  | 'FINALIZATION_RETRY_SCHEDULED'
  | 'FINALIZATION_COMPLETED'
  | 'FINALIZATION_CONFLICT'
  | 'FINALIZATION_REJECTED'
  | 'FINALIZATION_FAILED_TERMINAL';

export interface AisleFinalizationIntentRow {
  readonly id: string;
  readonly capture_session_id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly finalization_id: string;
  readonly expected_asset_count: number;
  readonly status: FinalizationIntentStatus;
  readonly last_error_code: string | null;
  readonly attempt_count: number;
  readonly next_retry_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class AisleFinalizationIntentRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async getBySession(sessionId: string): Promise<AisleFinalizationIntentRow | null> {
    return this.db.getFirstAsync<AisleFinalizationIntentRow>(
      `SELECT * FROM aisle_finalization_intents WHERE capture_session_id = ? LIMIT 1;`,
      sessionId,
    );
  }

  async upsertPending(input: {
    readonly id: string;
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly finalizationId: string;
    readonly expectedAssetCount: number;
    readonly nowIso: string;
  }): Promise<void> {
    const existing = await this.getBySession(input.sessionId);
    if (existing) {
      await this.db.runAsync(
        `UPDATE aisle_finalization_intents
         SET finalization_id = ?, expected_asset_count = ?, status = 'FINALIZATION_PENDING',
             last_error_code = NULL, updated_at = ?
         WHERE capture_session_id = ?;`,
        input.finalizationId,
        input.expectedAssetCount,
        input.nowIso,
        input.sessionId,
      );
      return;
    }
    await this.db.runAsync(
      `INSERT INTO aisle_finalization_intents (
         id, capture_session_id, inventory_id, aisle_id, finalization_id,
         expected_asset_count, status, last_error_code, attempt_count, next_retry_at,
         created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, 'FINALIZATION_PENDING', NULL, 0, NULL, ?, ?);`,
      input.id,
      input.sessionId,
      input.inventoryId,
      input.aisleId,
      input.finalizationId,
      input.expectedAssetCount,
      input.nowIso,
      input.nowIso,
    );
  }

  async updateStatus(
    sessionId: string,
    status: FinalizationIntentStatus,
    opts: { errorCode?: string | null; nowIso: string; bumpAttempt?: boolean } ,
  ): Promise<void> {
    if (opts.bumpAttempt) {
      await this.db.runAsync(
        `UPDATE aisle_finalization_intents
         SET status = ?, last_error_code = ?, attempt_count = attempt_count + 1, updated_at = ?
         WHERE capture_session_id = ?;`,
        status,
        opts.errorCode ?? null,
        opts.nowIso,
        sessionId,
      );
      return;
    }
    await this.db.runAsync(
      `UPDATE aisle_finalization_intents
       SET status = ?, last_error_code = ?, updated_at = ?
       WHERE capture_session_id = ?;`,
      status,
      opts.errorCode ?? null,
      opts.nowIso,
      sessionId,
    );
  }
}
