/**
 * Phase 9 offline operations — public exports.
 */

export {
  OFFLINE_OPERATION_TYPES,
  OFFLINE_OPERATION_STATUSES,
  OFFLINE_PRIORITY,
  buildIdempotencyKey,
  classifyHttpOrNetworkError,
  isTerminalStatus,
  isRunnableStatus,
  type OfflineOperationType,
  type OfflineOperationStatus,
  type OfflineOperationRow,
  type OfflineErrorClass,
} from './offlineOperationTypes';
export {
  computeBackoffMs,
  nextRetryIso,
  OFFLINE_RETRY_SCHEDULE_MS,
} from './offlineRetryPolicy';
export {
  selectEligibleOperations,
  dependenciesSatisfied,
  recoverAbandonedRunningStatus,
  type DependencyEdge,
} from './offlineDependencyResolver';
export {
  buildAisleSessionProjection,
  getPrimaryAisleAction,
  type AisleSessionProjection,
  type PrimaryAisleAction,
} from './aisleSessionProjection';
export {
  encodePayload,
  decodePayloadForOperation,
  decodeUploadAssetPayloadV1,
  decodeFinalizeAislePayloadV1,
  decodeStartServerProcessingPayloadV1,
  decodeSyncAuthoritativeResultPayloadV1,
  decodeApplyLocalResultsPayloadV1,
  decodeCreateServerReprocessPayloadV1,
  decodeAdoptServerProposalsPayloadV1,
  decodeSyncAisleRevisionPayloadV1,
  decodeApplyAisleRevisionPayloadV1,
} from './offlinePayloads';
export { computeOfflinePayloadHash, canonicalizeOfflinePayload } from './offlinePayloadHash';
export {
  mapDomainOutcomeToExecutor,
  type DomainOperationOutcome,
} from './domainOperationOutcome';
export { OfflineOperationScheduler } from './offlineOperationScheduler';
export {
  createOfflineOperationFacade,
  type OfflineOperationFacade,
} from './offlineOperationBridge';
export { buildDirectedExecutorMap } from './offlineDirectedExecutors';
export { createOfflineAutoEnqueue } from './offlineAutoEnqueue';
export { subscribeAuthState, emitAuthState } from './authStateEvents';
