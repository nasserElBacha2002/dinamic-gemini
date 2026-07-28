import type { Logger } from '../../core/logging';
import type { OfflineOperationRepository } from '../../database/repositories/offlineOperationRepository';
import { createId } from '../../shared/createId';
import {
  buildIdempotencyKey,
  OFFLINE_PRIORITY,
  type OfflineOperationType,
} from './offlineOperationTypes';
import { encodePayload, type OfflinePayloadV1 } from './offlinePayloads';

/**
 * Facade: persist intention before execution. Does not register ADOPT_SERVER_PROPOSALS
 * until a real adoption executor exists.
 */

export type OfflineOperationFacade = {
  readonly enqueueUploadAsset: (input: {
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly capturePhotoId: string;
    readonly assetId: string;
    readonly localFilePath: string;
    readonly sha256: string;
    readonly preparedMimeType: string;
    readonly byteSize: number;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueFinalizeAisle: (input: {
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly finalizationId: string;
    readonly expectedAssetCount: number;
    readonly baseReadinessVersion: string;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueStartServerProcessing: (input: {
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly processingPlanVersion: string;
    readonly requestId: string;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueSyncAuthoritativeResult: (input: {
    readonly resultId: string;
    readonly contentHash: string;
    readonly capturePhotoId: string;
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueApplyLocalResults: (input: {
    readonly sessionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly expectedResultIds: readonly string[];
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueCreateServerReprocess: (input: {
    readonly requestId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly scopeType: string;
    readonly scopeJson: string;
    readonly processingMode: string;
    readonly reason: string;
    readonly sessionId?: string;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueSyncAisleRevision: (input: {
    readonly revisionId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly sessionId?: string;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
  readonly enqueueApplyAisleRevision: (input: {
    readonly revisionId: string;
    readonly applyId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly expectedBaseFinalizationId: string;
    readonly appliedBy: string;
    readonly sessionId?: string;
    readonly dependsOnOperationIds?: readonly string[];
  }) => Promise<string>;
};

export function createOfflineOperationFacade(input: {
  readonly repo: OfflineOperationRepository;
  readonly logger: Logger;
}): OfflineOperationFacade {
  const enqueue = async (args: {
    readonly type: OfflineOperationType;
    readonly entityType: string;
    readonly entityId: string;
    readonly inventoryId: string;
    readonly aisleId: string;
    readonly assetId?: string;
    readonly sessionId?: string;
    readonly idempotencyKey: string;
    readonly payload: OfflinePayloadV1;
    readonly priority: number;
    readonly dependsOnOperationIds?: readonly string[];
  }): Promise<string> => {
    if (args.type === 'ADOPT_SERVER_PROPOSALS') {
      throw new Error('ADOPT_SERVER_PROPOSALS_NOT_IMPLEMENTED');
    }
    const operationId = createId();
    const nowIso = new Date().toISOString();
    const result = await input.repo.enqueue({
      operationId,
      operationType: args.type,
      entityType: args.entityType,
      entityId: args.entityId,
      inventoryId: args.inventoryId,
      aisleId: args.aisleId,
      assetId: args.assetId ?? null,
      sessionId: args.sessionId ?? null,
      payloadJson: encodePayload(args.payload),
      payloadVersion: 1,
      idempotencyKey: args.idempotencyKey,
      priority: args.priority,
      nowIso,
      ...(args.dependsOnOperationIds
        ? { dependsOnOperationIds: args.dependsOnOperationIds }
        : {}),
    });
    if (result.kind === 'payload_conflict') {
      throw new Error('IDEMPOTENCY_PAYLOAD_CONFLICT');
    }
    if (result.kind === 'existing') {
      return result.operationId;
    }
    input.logger.info('recovery', {
      obs: true,
      obs_name: 'offline_operation_created',
      operation_type: args.type,
    });
    return result.operationId;
  };

  return {
    enqueueUploadAsset: (p) =>
      enqueue({
        type: 'UPLOAD_ASSET',
        entityType: 'asset',
        entityId: p.assetId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        assetId: p.assetId,
        sessionId: p.sessionId,
        idempotencyKey: buildIdempotencyKey('UPLOAD_ASSET', [p.assetId, p.sha256]),
        priority: OFFLINE_PRIORITY.UPLOAD,
        payload: {
          localFilePath: p.localFilePath,
          assetId: p.assetId,
          capturePhotoId: p.capturePhotoId,
          sha256: p.sha256,
          preparedMimeType: p.preparedMimeType,
          byteSize: p.byteSize,
          sessionId: p.sessionId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
        },
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueFinalizeAisle: (p) =>
      enqueue({
        type: 'FINALIZE_AISLE',
        entityType: 'aisle',
        entityId: p.aisleId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        sessionId: p.sessionId,
        idempotencyKey: buildIdempotencyKey('FINALIZE_AISLE', [p.finalizationId]),
        priority: OFFLINE_PRIORITY.FINALIZE,
        payload: {
          sessionId: p.sessionId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
          finalizationId: p.finalizationId,
          expectedAssetCount: p.expectedAssetCount,
          baseReadinessVersion: p.baseReadinessVersion,
        },
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueStartServerProcessing: (p) =>
      enqueue({
        type: 'START_SERVER_PROCESSING',
        entityType: 'aisle',
        entityId: p.aisleId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        sessionId: p.sessionId,
        idempotencyKey: buildIdempotencyKey('START_SERVER_PROCESSING', [
          p.aisleId,
          p.processingPlanVersion,
          p.requestId,
        ]),
        priority: OFFLINE_PRIORITY.SERVER_PROCESS,
        payload: {
          sessionId: p.sessionId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
          processingPlanVersion: p.processingPlanVersion,
          requestId: p.requestId,
        },
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueSyncAuthoritativeResult: (p) =>
      enqueue({
        type: 'SYNC_AUTHORITATIVE_RESULT',
        entityType: 'result',
        entityId: p.resultId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        sessionId: p.sessionId,
        idempotencyKey: buildIdempotencyKey('SYNC_AUTHORITATIVE_RESULT', [
          p.resultId,
          p.contentHash,
        ]),
        priority: OFFLINE_PRIORITY.SYNC,
        payload: {
          resultId: p.resultId,
          contentHash: p.contentHash,
          capturePhotoId: p.capturePhotoId,
          sessionId: p.sessionId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
        },
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueApplyLocalResults: (p) =>
      enqueue({
        type: 'APPLY_LOCAL_RESULTS',
        entityType: 'aisle',
        entityId: p.aisleId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        sessionId: p.sessionId,
        idempotencyKey: buildIdempotencyKey('APPLY_LOCAL_RESULTS', [
          p.aisleId,
          [...p.expectedResultIds].sort().join(','),
        ]),
        priority: OFFLINE_PRIORITY.APPLY,
        payload: {
          sessionId: p.sessionId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
          expectedResultIds: p.expectedResultIds,
        },
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueCreateServerReprocess: (p) =>
      enqueue({
        type: 'CREATE_SERVER_REPROCESS',
        entityType: 'aisle',
        entityId: p.aisleId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        idempotencyKey: buildIdempotencyKey('CREATE_SERVER_REPROCESS', [p.requestId]),
        priority: OFFLINE_PRIORITY.SERVER_PROCESS,
        payload: {
          requestId: p.requestId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
          scopeType: p.scopeType,
          scopeJson: p.scopeJson,
          processingMode: p.processingMode,
          reason: p.reason,
        },
        ...(p.sessionId ? { sessionId: p.sessionId } : {}),
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueSyncAisleRevision: (p) =>
      enqueue({
        type: 'SYNC_AISLE_REVISION',
        entityType: 'revision',
        entityId: p.revisionId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        idempotencyKey: buildIdempotencyKey('SYNC_AISLE_REVISION', [p.revisionId]),
        priority: OFFLINE_PRIORITY.REVISION,
        payload: {
          revisionId: p.revisionId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
        },
        ...(p.sessionId ? { sessionId: p.sessionId } : {}),
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
    enqueueApplyAisleRevision: (p) =>
      enqueue({
        type: 'APPLY_AISLE_REVISION',
        entityType: 'revision',
        entityId: p.revisionId,
        inventoryId: p.inventoryId,
        aisleId: p.aisleId,
        idempotencyKey: buildIdempotencyKey('APPLY_AISLE_REVISION', [p.applyId]),
        priority: OFFLINE_PRIORITY.REVISION,
        payload: {
          revisionId: p.revisionId,
          applyId: p.applyId,
          inventoryId: p.inventoryId,
          aisleId: p.aisleId,
          expectedBaseFinalizationId: p.expectedBaseFinalizationId,
          appliedBy: p.appliedBy,
        },
        ...(p.sessionId ? { sessionId: p.sessionId } : {}),
        ...(p.dependsOnOperationIds
          ? { dependsOnOperationIds: p.dependsOnOperationIds }
          : {}),
      }),
  };
}
