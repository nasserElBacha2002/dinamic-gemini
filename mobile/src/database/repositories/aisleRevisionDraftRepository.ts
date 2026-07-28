import type { SQLiteDatabase } from 'expo-sqlite';

export type AisleRevisionDraftStatus =
  | 'REVISION_DRAFT_LOCAL'
  | 'REVISION_SYNC_PENDING'
  | 'REVISION_SYNCED'
  | 'REVISION_APPLY_PENDING'
  | 'REVISION_COMPLETED'
  | 'REVISION_CONFLICT';

export type AisleRevisionDraftSyncStatus = 'LOCAL' | 'PENDING' | 'SYNCED' | 'FAILED';

export interface AisleRevisionDraftRow {
  readonly revision_id: string;
  readonly inventory_id: string;
  readonly aisle_id: string;
  readonly base_finalization_id: string | null;
  readonly status: AisleRevisionDraftStatus;
  readonly pending_changes_json: string;
  readonly sync_status: AisleRevisionDraftSyncStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface AisleRevisionPendingChanges {
  readonly revision_type: string;
  readonly reason: string;
  readonly requested_by: string;
  readonly items: readonly {
    readonly asset_id: string;
    readonly internal_code?: string | null;
    readonly quantity?: number | null;
    readonly exclusion_action?: 'EXCLUDE' | 'RESTORE' | null;
    readonly reason?: string | null;
  }[];
}

export class AisleRevisionDraftRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async upsertDraft(input: {
    readonly revisionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly baseFinalizationId: string | null;
    readonly status: AisleRevisionDraftStatus;
    readonly pendingChanges: AisleRevisionPendingChanges;
    readonly syncStatus: AisleRevisionDraftSyncStatus;
    readonly nowIso: string;
  }): Promise<void> {
    const pendingJson = JSON.stringify(input.pendingChanges);
    const existing = await this.db.getFirstAsync<{ revision_id: string }>(
      `SELECT revision_id FROM aisle_revision_drafts WHERE revision_id = ? LIMIT 1;`,
      input.revisionId,
    );
    if (existing) {
      await this.db.runAsync(
        `UPDATE aisle_revision_drafts
         SET base_finalization_id = ?, status = ?, pending_changes_json = ?,
             sync_status = ?, updated_at = ?
         WHERE revision_id = ?;`,
        input.baseFinalizationId,
        input.status,
        pendingJson,
        input.syncStatus,
        input.nowIso,
        input.revisionId,
      );
      return;
    }
    await this.db.runAsync(
      `INSERT INTO aisle_revision_drafts (
         revision_id, inventory_id, aisle_id, base_finalization_id,
         status, pending_changes_json, sync_status, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);`,
      input.revisionId,
      input.inventoryId,
      input.aisleId,
      input.baseFinalizationId,
      input.status,
      pendingJson,
      input.syncStatus,
      input.nowIso,
      input.nowIso,
    );
  }

  async getDraft(revisionId: string): Promise<AisleRevisionDraftRow | null> {
    const row = await this.db.getFirstAsync<AisleRevisionDraftRow>(
      `SELECT * FROM aisle_revision_drafts WHERE revision_id = ? LIMIT 1;`,
      revisionId,
    );
    return row ?? null;
  }

  async listForAisle(inventoryId: string, aisleId: string): Promise<AisleRevisionDraftRow[]> {
    const rows = await this.db.getAllAsync<AisleRevisionDraftRow>(
      `SELECT * FROM aisle_revision_drafts
       WHERE inventory_id = ? AND aisle_id = ?
       ORDER BY updated_at DESC;`,
      inventoryId,
      aisleId,
    );
    return rows ?? [];
  }

  async listPendingSync(limit = 20): Promise<AisleRevisionDraftRow[]> {
    const rows = await this.db.getAllAsync<AisleRevisionDraftRow>(
      `SELECT * FROM aisle_revision_drafts
       WHERE sync_status IN ('LOCAL', 'PENDING')
         AND status IN ('REVISION_DRAFT_LOCAL', 'REVISION_SYNC_PENDING')
       ORDER BY created_at ASC
       LIMIT ?;`,
      limit,
    );
    return rows ?? [];
  }

  async updateStatus(input: {
    readonly revisionId: string;
    readonly status: AisleRevisionDraftStatus;
    readonly syncStatus?: AisleRevisionDraftSyncStatus;
    readonly baseFinalizationId?: string | null;
    readonly nowIso: string;
  }): Promise<void> {
    if (input.baseFinalizationId !== undefined) {
      await this.db.runAsync(
        `UPDATE aisle_revision_drafts
         SET status = ?, sync_status = COALESCE(?, sync_status),
             base_finalization_id = ?, updated_at = ?
         WHERE revision_id = ?;`,
        input.status,
        input.syncStatus ?? null,
        input.baseFinalizationId,
        input.nowIso,
        input.revisionId,
      );
      return;
    }
    await this.db.runAsync(
      `UPDATE aisle_revision_drafts
       SET status = ?, sync_status = COALESCE(?, sync_status), updated_at = ?
       WHERE revision_id = ?;`,
      input.status,
      input.syncStatus ?? null,
      input.nowIso,
      input.revisionId,
    );
  }
}
