/**
 * Phase 9 corrections — entity-directed executors (no global drain → COMPLETED).
 */

import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import type { AisleRevisionDraftRepository } from '../../database/repositories/aisleRevisionDraftRepository';
import type { ServerReprocessIntentRepository } from '../../database/repositories/serverReprocessIntentRepository';
import type { AisleFinalizationIntentRepository } from '../../database/repositories/aisleFinalizationIntentRepository';
import type { AuthoritativeLocalResultSyncService } from '../authoritativeLocalResult/authoritativeLocalResultSyncService';
import type { AuthoritativeAisleFinalizationService } from '../authoritativeAisleFinalization/authoritativeAisleFinalizationService';
import type { ServerReprocessService } from '../serverReprocess/serverReprocessService';
import type { AisleRevisionService } from '../aisleRevision/aisleRevisionService';
import type { ProcessingService } from '../processing/processingService';
import type { DomainOperationOutcome } from './domainOperationOutcome';
import { mapDomainOutcomeToExecutor } from './domainOperationOutcome';
import {
  decodeApplyLocalResultsPayloadV1,
  decodeCreateServerReprocessPayloadV1,
  decodeFinalizeAislePayloadV1,
  decodePayloadForOperation,
  decodeStartServerProcessingPayloadV1,
  decodeSyncAuthoritativeResultPayloadV1,
  decodeUploadAssetPayloadV1,
  decodeSyncAisleRevisionPayloadV1,
  decodeApplyAisleRevisionPayloadV1,
} from './offlinePayloads';
import type { OfflineOperationRow, OfflineOperationType } from './offlineOperationTypes';
import type { OfflineExecutorResult, OfflineOperationExecutor } from './offlineOperationScheduler';
import { ApiError } from '../../services/api/apiClient';
import { classifyHttpOrNetworkError } from './offlineOperationTypes';

function fromApiError(error: unknown): DomainOperationOutcome {
  if (error instanceof ApiError) {
    const klass = classifyHttpOrNetworkError({
      httpStatus: error.status,
      code: error.code,
      message: error.message,
    });
    if (klass === 'auth') {
      return { status: 'auth', code: error.code ?? 'UNAUTHORIZED', message: error.message };
    }
    if (klass === 'conflict') {
      return { status: 'conflict', code: error.code ?? 'CONFLICT', message: error.message };
    }
    if (klass === 'terminal') {
      return { status: 'terminal', code: error.code ?? 'TERMINAL', message: error.message };
    }
    return { status: 'retryable', code: error.code ?? 'RETRYABLE', message: error.message };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { status: 'retryable', code: 'EXECUTOR_THREW', message };
}

export type DirectedExecutorHooks = {
  readonly wakeUploadQueue: () => Promise<void>;
  readonly capture: CaptureRepository;
  readonly confirmed: ConfirmedLocalResultRepository;
  readonly authoritativeSync: AuthoritativeLocalResultSyncService;
  readonly finalization: AuthoritativeAisleFinalizationService;
  readonly finalizationIntents: AisleFinalizationIntentRepository | null;
  readonly serverReprocess: ServerReprocessService;
  readonly serverReprocessIntents: ServerReprocessIntentRepository | null;
  readonly aisleRevision: AisleRevisionService;
  readonly aisleRevisionDrafts: AisleRevisionDraftRepository | null;
  readonly processing: ProcessingService;
};

async function executeUploadAsset(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    decodePayloadForOperation(op.operation_type, op.payload_version, op.payload_json);
    const payload = decodeUploadAssetPayloadV1(op.payload_json);
    await hooks.wakeUploadQueue();
    const photo = await hooks.capture.getPhotoById(payload.capturePhotoId);
    if (!photo) {
      return {
        status: 'terminal',
        code: 'LOCAL_FILE_MISSING',
        message: 'Capture photo not found',
      };
    }
    if (photo.upload_status === 'uploaded' || photo.upload_status === 'excluded') {
      return photo.backend_asset_id
        ? { status: 'completed', remoteId: photo.backend_asset_id }
        : { status: 'completed' };
    }
    if (photo.upload_status === 'permanent_error') {
      return {
        status: 'terminal',
        code: 'UPLOAD_TERMINAL',
        message: `upload_status=${photo.upload_status}`,
      };
    }
    return {
      status: 'pending',
      code: 'UPLOAD_IN_PROGRESS',
      message: `upload_status=${photo.upload_status}`,
    };
  } catch (error) {
    if (error instanceof Error && error.message === 'UNSUPPORTED_PAYLOAD_VERSION') {
      return { status: 'terminal', code: 'UNSUPPORTED_PAYLOAD_VERSION', message: error.message };
    }
    return fromApiError(error);
  }
}

async function executeSyncAuthoritative(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeSyncAuthoritativeResultPayloadV1(op.payload_json);
    const row = await hooks.confirmed.getById(payload.resultId);
    if (!row) {
      return {
        status: 'terminal',
        code: 'RESULT_NOT_FOUND',
        message: 'Confirmed result missing',
      };
    }
    if (row.sync_status === 'SYNCED') {
      return { status: 'completed' };
    }
    if (row.sync_status === 'CONFLICT') {
      return { status: 'conflict', code: 'RESULT_STALE', message: 'Authoritative sync conflict' };
    }
    if (row.sync_status === 'FAILED_TERMINAL' || row.sync_status === 'REJECTED') {
      return {
        status: 'terminal',
        code: row.sync_last_error_code ?? row.sync_status,
        message: row.sync_last_error_code ?? row.sync_status,
      };
    }
    await hooks.authoritativeSync.syncPending();
    const after = await hooks.confirmed.getById(payload.resultId);
    if (after?.sync_status === 'SYNCED') {
      return { status: 'completed' };
    }
    if (after?.sync_status === 'CONFLICT') {
      return { status: 'conflict', code: 'RESULT_STALE' };
    }
    return {
      status: 'pending',
      code: 'SYNC_PENDING',
      message: `sync_status=${after?.sync_status ?? 'missing'}`,
    };
  } catch (error) {
    return fromApiError(error);
  }
}

async function executeApplyLocalResults(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeApplyLocalResultsPayloadV1(op.payload_json);
    if (payload.expectedResultIds.length === 0) {
      return {
        status: 'terminal',
        code: 'INVALID_PAYLOAD',
        message: 'expectedResultIds empty',
      };
    }
    let allSynced = true;
    let allApplied = true;
    for (const resultId of payload.expectedResultIds) {
      const row = await hooks.confirmed.getById(resultId);
      if (!row) {
        return {
          status: 'dependency',
          code: 'RESULT_MISSING',
          message: `Missing result ${resultId}`,
        };
      }
      if (row.sync_status === 'CONFLICT') {
        return { status: 'conflict', code: 'RESULT_STALE', message: resultId };
      }
      if (row.sync_status === 'FAILED_TERMINAL' || row.sync_status === 'REJECTED') {
        return {
          status: 'terminal',
          code: row.sync_last_error_code ?? row.sync_status,
          message: resultId,
        };
      }
      if (row.sync_status !== 'SYNCED') {
        allSynced = false;
      }
      if (!row.applied_at) {
        allApplied = false;
      }
    }
    if (!allSynced) {
      return {
        status: 'dependency',
        code: 'RESULTS_NOT_SYNCED',
        message: 'Waiting for authoritative sync of all results',
      };
    }
    // Positions may be applied at process/finalize; SYNCED without applied_at is apply-ready.
    if (allApplied) {
      return { status: 'completed' };
    }
    return { status: 'completed' };
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('INVALID_PAYLOAD')) {
      return { status: 'terminal', code: 'INVALID_PAYLOAD', message: error.message };
    }
    return fromApiError(error);
  }
}

async function executeFinalize(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeFinalizeAislePayloadV1(op.payload_json);
    const intent = hooks.finalizationIntents
      ? await hooks.finalizationIntents.getBySession(payload.sessionId)
      : null;
    // Prefer service finalize for this session only.
    const result = await hooks.finalization.finalize({
      sessionId: payload.sessionId,
      inventoryId: payload.inventoryId,
      aisleId: payload.aisleId,
    });
    if (result.ok) {
      return { status: 'completed' };
    }
    const code = result.code ?? 'FINALIZE_FAILED';
    if (code.includes('CONFLICT') || code.includes('STALE') || code === 'FINALIZATION_CONFLICT') {
      return { status: 'conflict', code: 'FINALIZATION_STALE', message: result.reason };
    }
    if (code === 'UNAUTHORIZED' || code.includes('AUTH')) {
      return { status: 'auth', code, message: result.reason };
    }
    if (code === 'IN_FLIGHT' || code === 'FINALIZATION_PENDING') {
      return { status: 'pending', code, message: result.reason };
    }
    if (intent?.status === 'FINALIZATION_COMPLETED') {
      return { status: 'completed' };
    }
    return { status: 'retryable', code, message: result.reason };
  } catch (error) {
    return fromApiError(error);
  }
}

async function executeStartServerProcessing(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeStartServerProcessingPayloadV1(op.payload_json);
    const result = await hooks.processing.startProcess(payload.sessionId);
    if (result.ok && result.jobId) {
      return { status: 'completed', remoteId: result.jobId };
    }
    if (result.ok) {
      return { status: 'completed' };
    }
    return {
      status: 'pending',
      code: 'PROCESS_NOT_READY',
      message: result.reason ?? 'not ready',
    };
  } catch (error) {
    return fromApiError(error);
  }
}

async function executeCreateServerReprocess(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeCreateServerReprocessPayloadV1(op.payload_json);
    if (hooks.serverReprocessIntents) {
      const intent = await hooks.serverReprocessIntents.getByRequestId(payload.requestId);
      if (intent?.status === 'COMPLETED' && intent.server_run_id) {
        return { status: 'completed', remoteId: intent.server_run_id };
      }
    }
    const scope = JSON.parse(payload.scopeJson) as {
      type: string;
      asset_ids?: string[];
    };
    const run = await hooks.serverReprocess.requestReprocess({
      inventoryId: payload.inventoryId,
      aisleId: payload.aisleId,
      scopeType: scope.type as
        | 'FULL_AISLE'
        | 'SELECTED_ASSETS'
        | 'FAILED_ONLY'
        | 'UNRECOGNIZED_ONLY'
        | 'PENDING_REVIEW_ONLY',
      processingMode: payload.processingMode as
        | 'CODE_SCAN'
        | 'INTERNAL_OCR'
        | 'GLOBAL_FALLBACK'
        | 'AUTO_PIPELINE',
      reason: payload.reason,
      offline: false,
      ...(scope.asset_ids ? { assetIds: scope.asset_ids } : {}),
    });
    if ('pending' in run && run.pending) {
      return { status: 'pending', code: 'REPROCESS_PENDING', message: run.request_id };
    }
    if ('id' in run) {
      return { status: 'completed', remoteId: run.id };
    }
    return { status: 'retryable', code: 'REPROCESS_UNKNOWN', message: 'unexpected response' };
  } catch (error) {
    return fromApiError(error);
  }
}

async function executeSyncRevision(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeSyncAisleRevisionPayloadV1(op.payload_json);
    const draft = hooks.aisleRevisionDrafts
      ? await hooks.aisleRevisionDrafts.getDraft(payload.revisionId)
      : null;
    if (
      draft &&
      (draft.sync_status === 'SYNCED' ||
        draft.status === 'REVISION_SYNCED' ||
        draft.status === 'REVISION_COMPLETED')
    ) {
      return { status: 'completed' };
    }
    const n = await hooks.aisleRevision.syncPendingDrafts(20);
    const after = hooks.aisleRevisionDrafts
      ? await hooks.aisleRevisionDrafts.getDraft(payload.revisionId)
      : null;
    if (
      after &&
      (after.sync_status === 'SYNCED' ||
        after.status === 'REVISION_SYNCED' ||
        after.status === 'REVISION_COMPLETED')
    ) {
      return { status: 'completed' };
    }
    if (after && after.status === 'REVISION_CONFLICT') {
      return { status: 'conflict', code: 'REVISION_STALE' };
    }
    return {
      status: 'pending',
      code: 'REVISION_SYNC_PENDING',
      message: `synced_batch=${n}`,
    };
  } catch (error) {
    return fromApiError(error);
  }
}

async function executeApplyRevision(
  op: OfflineOperationRow,
  hooks: DirectedExecutorHooks,
): Promise<DomainOperationOutcome> {
  try {
    const payload = decodeApplyAisleRevisionPayloadV1(op.payload_json);
    await hooks.aisleRevision.applyRevision({
      inventoryId: payload.inventoryId,
      aisleId: payload.aisleId,
      revisionId: payload.revisionId,
      expectedBaseFinalizationId: payload.expectedBaseFinalizationId,
      appliedBy: payload.appliedBy,
    });
    return { status: 'completed' };
  } catch (error) {
    return fromApiError(error);
  }
}

function wrap(
  type: OfflineOperationType,
  run: (op: OfflineOperationRow) => Promise<DomainOperationOutcome>,
): OfflineOperationExecutor {
  return {
    type,
    execute: async (op) => mapDomainOutcomeToExecutor(await run(op)),
  };
}

/**
 * ADOPT_SERVER_PROPOSALS is intentionally omitted until a real adoption executor ships.
 */
export function buildDirectedExecutorMap(
  hooks: DirectedExecutorHooks,
): Map<OfflineOperationType, OfflineOperationExecutor> {
  const map = new Map<OfflineOperationType, OfflineOperationExecutor>();
  map.set('UPLOAD_ASSET', wrap('UPLOAD_ASSET', (op) => executeUploadAsset(op, hooks)));
  map.set(
    'SYNC_AUTHORITATIVE_RESULT',
    wrap('SYNC_AUTHORITATIVE_RESULT', (op) => executeSyncAuthoritative(op, hooks)),
  );
  map.set(
    'APPLY_LOCAL_RESULTS',
    wrap('APPLY_LOCAL_RESULTS', (op) => executeApplyLocalResults(op, hooks)),
  );
  map.set('FINALIZE_AISLE', wrap('FINALIZE_AISLE', (op) => executeFinalize(op, hooks)));
  map.set(
    'START_SERVER_PROCESSING',
    wrap('START_SERVER_PROCESSING', (op) => executeStartServerProcessing(op, hooks)),
  );
  map.set(
    'CREATE_SERVER_REPROCESS',
    wrap('CREATE_SERVER_REPROCESS', (op) => executeCreateServerReprocess(op, hooks)),
  );
  map.set(
    'SYNC_AISLE_REVISION',
    wrap('SYNC_AISLE_REVISION', (op) => executeSyncRevision(op, hooks)),
  );
  map.set(
    'APPLY_AISLE_REVISION',
    wrap('APPLY_AISLE_REVISION', (op) => executeApplyRevision(op, hooks)),
  );
  return map;
}

export type { OfflineExecutorResult };
