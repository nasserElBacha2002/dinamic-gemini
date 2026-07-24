import type {
  AisleRevisionDraftRepository,
  AisleRevisionPendingChanges,
} from '../../database/repositories/aisleRevisionDraftRepository';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type {
  AisleRevisionApi,
  AisleRevisionDiffDto,
  AisleRevisionDto,
  AisleRevisionHistoryEntryDto,
  AisleRevisionType,
} from './aisleRevisionApi';

function newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export class AisleRevisionService {
  constructor(
    private readonly api: AisleRevisionApi,
    private readonly drafts: AisleRevisionDraftRepository | null,
    private readonly connectivity: ConnectivityService | null,
    private readonly flags: {
      readonly mobileAisleRevisions: boolean;
      readonly mobileAisleHistory: boolean;
      readonly serverAisleRevisions: boolean;
      readonly serverAisleRollback: boolean;
    },
  ) {}

  isActionVisible(): boolean {
    return Boolean(this.flags.mobileAisleRevisions);
  }

  isHistoryVisible(): boolean {
    return Boolean(this.flags.mobileAisleHistory);
  }

  isRollbackVisible(): boolean {
    return Boolean(this.flags.mobileAisleHistory && this.flags.serverAisleRollback);
  }

  private isOnline(): boolean {
    if (!this.connectivity) {
      return true;
    }
    return this.connectivity.getState() === 'online';
  }

  private assertRevisionEnabled(): void {
    if (!this.flags.mobileAisleRevisions) {
      throw new Error('Las correcciones de pasillo están deshabilitadas');
    }
  }

  private assertServerEnabled(): void {
    if (!this.flags.serverAisleRevisions) {
      throw new Error('Las correcciones en servidor están deshabilitadas');
    }
  }

  /**
   * Apply always requires network — offline drafts can be saved locally but not applied.
   */
  private assertOnlineForApply(): void {
    if (!this.isOnline()) {
      throw new Error('Se necesita conexión para aplicar la corrección');
    }
  }

  async createRevision(input: {
    inventoryId: string;
    aisleId: string;
    revisionType: AisleRevisionType;
    reason: string;
    requestedBy: string;
    revisionId?: string;
  }): Promise<
    | { local: true; revision_id: string }
    | { local: false; revision: AisleRevisionDto }
  > {
    this.assertRevisionEnabled();
    const revisionId = input.revisionId ?? newId('rev');
    const nowIso = new Date().toISOString();
    const pendingChanges: AisleRevisionPendingChanges = {
      revision_type: input.revisionType,
      reason: input.reason,
      requested_by: input.requestedBy,
      items: [],
    };

    if (!this.isOnline() || !this.flags.serverAisleRevisions) {
      if (!this.drafts) {
        throw new Error('No se puede guardar borrador sin almacenamiento local');
      }
      await this.drafts.upsertDraft({
        revisionId,
        inventoryId: input.inventoryId,
        aisleId: input.aisleId,
        baseFinalizationId: null,
        status: 'REVISION_DRAFT_LOCAL',
        pendingChanges,
        syncStatus: 'LOCAL',
        nowIso,
      });
      return { local: true, revision_id: revisionId };
    }

    try {
      const revision = await this.api.createRevision(input.inventoryId, input.aisleId, {
        revision_id: revisionId,
        revision_type: input.revisionType,
        reason: input.reason,
        requested_by: input.requestedBy,
      });
      if (this.drafts) {
        await this.drafts.upsertDraft({
          revisionId,
          inventoryId: input.inventoryId,
          aisleId: input.aisleId,
          baseFinalizationId: revision.base_finalization_id,
          status: 'REVISION_SYNCED',
          pendingChanges,
          syncStatus: 'SYNCED',
          nowIso,
        });
      }
      return { local: false, revision };
    } catch (error) {
      if (this.drafts) {
        await this.drafts.upsertDraft({
          revisionId,
          inventoryId: input.inventoryId,
          aisleId: input.aisleId,
          baseFinalizationId: null,
          status: 'REVISION_SYNC_PENDING',
          pendingChanges,
          syncStatus: 'PENDING',
          nowIso,
        });
        return { local: true, revision_id: revisionId };
      }
      throw error;
    }
  }

  async updateItem(input: {
    inventoryId: string;
    aisleId: string;
    revisionId: string;
    assetId: string;
    internalCode?: string | null;
    quantity?: number | null;
    exclusionAction?: 'EXCLUDE' | 'RESTORE' | null;
    reason?: string | null;
  }): Promise<void> {
    this.assertRevisionEnabled();
    const nowIso = new Date().toISOString();
    const draft = this.drafts ? await this.drafts.getDraft(input.revisionId) : null;

    if (draft) {
      const pending = JSON.parse(draft.pending_changes_json) as AisleRevisionPendingChanges;
      const items = pending.items.filter((i) => i.asset_id !== input.assetId);
      items.push({
        asset_id: input.assetId,
        ...(input.internalCode !== undefined ? { internal_code: input.internalCode } : {}),
        ...(input.quantity !== undefined ? { quantity: input.quantity } : {}),
        ...(input.exclusionAction !== undefined ? { exclusion_action: input.exclusionAction } : {}),
        ...(input.reason !== undefined ? { reason: input.reason } : {}),
      });
      await this.drafts!.upsertDraft({
        revisionId: input.revisionId,
        inventoryId: input.inventoryId,
        aisleId: input.aisleId,
        baseFinalizationId: draft.base_finalization_id,
        status: draft.status === 'REVISION_SYNCED' ? 'REVISION_SYNCED' : 'REVISION_DRAFT_LOCAL',
        pendingChanges: { ...pending, items },
        syncStatus: draft.sync_status,
        nowIso,
      });
    }

    if (!this.isOnline() || !this.flags.serverAisleRevisions) {
      return;
    }

    this.assertServerEnabled();
    await this.api.updateItem(
      input.inventoryId,
      input.aisleId,
      input.revisionId,
      input.assetId,
      {
        ...(input.internalCode !== undefined ? { internal_code: input.internalCode } : {}),
        ...(input.quantity !== undefined ? { quantity: input.quantity } : {}),
        ...(input.exclusionAction !== undefined ? { exclusion_action: input.exclusionAction } : {}),
        ...(input.reason !== undefined ? { reason: input.reason } : {}),
      },
    );
  }

  async getDiff(
    inventoryId: string,
    aisleId: string,
    revisionId: string,
  ): Promise<AisleRevisionDiffDto> {
    this.assertRevisionEnabled();
    this.assertServerEnabled();
    if (!this.isOnline()) {
      throw new Error('Se necesita conexión para consultar diferencias');
    }
    return this.api.getDiff(inventoryId, aisleId, revisionId);
  }

  async applyRevision(input: {
    inventoryId: string;
    aisleId: string;
    revisionId: string;
    expectedBaseFinalizationId: string;
    appliedBy: string;
  }): Promise<AisleRevisionDto> {
    this.assertRevisionEnabled();
    this.assertServerEnabled();
    this.assertOnlineForApply();

    const applyId = newId('apply');
    const revision = await this.api.apply(input.inventoryId, input.aisleId, input.revisionId, {
      apply_id: applyId,
      expected_base_finalization_id: input.expectedBaseFinalizationId,
      applied_by: input.appliedBy,
    });

    if (this.drafts) {
      await this.drafts.updateStatus({
        revisionId: input.revisionId,
        status: 'REVISION_COMPLETED',
        syncStatus: 'SYNCED',
        nowIso: new Date().toISOString(),
      });
    }
    return revision;
  }

  async getHistory(
    inventoryId: string,
    aisleId: string,
  ): Promise<readonly AisleRevisionHistoryEntryDto[]> {
    if (!this.isHistoryVisible()) {
      throw new Error('El historial de pasillo está deshabilitado');
    }
    this.assertServerEnabled();
    if (!this.isOnline()) {
      throw new Error('Se necesita conexión para consultar el historial');
    }
    return this.api.getHistory(inventoryId, aisleId);
  }

  async rollback(input: {
    inventoryId: string;
    aisleId: string;
    targetFinalizationId: string;
    reason: string;
    requestedBy: string;
  }): Promise<AisleRevisionDto> {
    if (!this.isRollbackVisible()) {
      throw new Error('La reversión de pasillo está deshabilitada');
    }
    this.assertServerEnabled();
    this.assertOnlineForApply();
    return this.api.rollback(input.inventoryId, input.aisleId, {
      rollback_id: newId('rollback'),
      target_finalization_id: input.targetFinalizationId,
      reason: input.reason,
      requested_by: input.requestedBy,
      apply_immediately: true,
    });
  }

  async syncPendingDrafts(limit = 10): Promise<number> {
    if (!this.flags.mobileAisleRevisions || !this.flags.serverAisleRevisions || !this.drafts) {
      return 0;
    }
    if (!this.isOnline()) {
      return 0;
    }
    const pending = await this.drafts.listPendingSync(limit);
    let synced = 0;
    for (const draft of pending) {
      try {
        const changes = JSON.parse(draft.pending_changes_json) as AisleRevisionPendingChanges;
        const revision = await this.api.createRevision(draft.inventory_id, draft.aisle_id, {
          revision_id: draft.revision_id,
          revision_type: changes.revision_type as AisleRevisionType,
          reason: changes.reason,
          requested_by: changes.requested_by,
        });
        for (const item of changes.items) {
          await this.api.updateItem(
            draft.inventory_id,
            draft.aisle_id,
            draft.revision_id,
            item.asset_id,
            {
              ...(item.internal_code !== undefined ? { internal_code: item.internal_code } : {}),
              ...(item.quantity !== undefined ? { quantity: item.quantity } : {}),
              ...(item.exclusion_action !== undefined
                ? { exclusion_action: item.exclusion_action }
                : {}),
              ...(item.reason !== undefined ? { reason: item.reason } : {}),
            },
          );
        }
        await this.drafts.updateStatus({
          revisionId: draft.revision_id,
          status: 'REVISION_SYNCED',
          syncStatus: 'SYNCED',
          baseFinalizationId: revision.base_finalization_id,
          nowIso: new Date().toISOString(),
        });
        synced += 1;
      } catch {
        // leave for next retry
      }
    }
    return synced;
  }
}
