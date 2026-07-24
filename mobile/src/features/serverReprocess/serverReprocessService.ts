import type { ServerReprocessIntentRepository } from '../../database/repositories/serverReprocessIntentRepository';
import type {
  ServerReprocessAdoptItem,
  ServerReprocessApi,
  ServerReprocessDetailDto,
  ServerReprocessProcessingMode,
  ServerReprocessRunDto,
  ServerReprocessScopeType,
} from './serverReprocessApi';

function newId(): string {
  return `sr-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export class ServerReprocessService {
  constructor(
    private readonly api: ServerReprocessApi,
    private readonly intents: ServerReprocessIntentRepository | null,
    private readonly flags: {
      readonly mobileServerReprocess: boolean;
      readonly mobileServerReprocessReview: boolean;
      readonly serverReprocessOfflineQueue: boolean;
    },
  ) {}

  isActionVisible(): boolean {
    return Boolean(this.flags.mobileServerReprocess);
  }

  isReviewVisible(): boolean {
    return Boolean(this.flags.mobileServerReprocess && this.flags.mobileServerReprocessReview);
  }

  async requestReprocess(input: {
    inventoryId: string;
    aisleId: string;
    scopeType: ServerReprocessScopeType;
    assetIds?: string[];
    processingMode: ServerReprocessProcessingMode;
    reason?: string;
    offline?: boolean;
  }): Promise<ServerReprocessRunDto | { pending: true; request_id: string }> {
    if (!this.flags.mobileServerReprocess) {
      throw new Error('Server reprocess is disabled');
    }
    const requestId = newId();
    const scopeJson = JSON.stringify({
      type: input.scopeType,
      asset_ids: input.assetIds ?? [],
    });
    const nowIso = new Date().toISOString();

    if (input.offline && this.flags.serverReprocessOfflineQueue && this.intents) {
      await this.intents.upsertPending({
        id: newId(),
        requestId,
        inventoryId: input.inventoryId,
        aisleId: input.aisleId,
        scopeType: input.scopeType,
        scopeJson,
        processingMode: input.processingMode,
        reason: input.reason ?? 'USER_REQUESTED_REPROCESS',
        nowIso,
      });
      return { pending: true, request_id: requestId };
    }

    try {
      const run = await this.api.requestReprocess(input.inventoryId, input.aisleId, {
        request_id: requestId,
        scope: { type: input.scopeType, asset_ids: input.assetIds ?? [] },
        processing_mode: input.processingMode,
        reason: input.reason ?? 'USER_REQUESTED_REPROCESS',
      });
      return run;
    } catch (error) {
      if (this.flags.serverReprocessOfflineQueue && this.intents) {
        await this.intents.upsertPending({
          id: newId(),
          requestId,
          inventoryId: input.inventoryId,
          aisleId: input.aisleId,
          scopeType: input.scopeType,
          scopeJson,
          processingMode: input.processingMode,
          reason: input.reason ?? 'USER_REQUESTED_REPROCESS',
          nowIso,
        });
        return { pending: true, request_id: requestId };
      }
      throw error;
    }
  }

  async getRun(
    inventoryId: string,
    aisleId: string,
    runId: string,
  ): Promise<ServerReprocessDetailDto> {
    return this.api.getRun(inventoryId, aisleId, runId);
  }

  async adopt(
    inventoryId: string,
    aisleId: string,
    runId: string,
    items: ServerReprocessAdoptItem[],
  ): Promise<{ adoption_id: string; review_status: string; replayed: boolean }> {
    if (!this.flags.mobileServerReprocessReview) {
      throw new Error('Server reprocess review is disabled');
    }
    return this.api.adopt(inventoryId, aisleId, runId, {
      adoption_id: newId(),
      items,
    });
  }
}
