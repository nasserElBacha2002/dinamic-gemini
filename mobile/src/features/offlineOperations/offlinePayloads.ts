/**
 * Phase 9 — versioned offline operation payloads (codecs + registry).
 */

import type { OfflineOperationType } from './offlineOperationTypes';

export type UploadAssetPayloadV1 = {
  readonly localFilePath: string;
  readonly assetId: string;
  readonly capturePhotoId: string;
  readonly sha256: string;
  readonly preparedMimeType: string;
  readonly byteSize: number;
  readonly sessionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
};

export type SyncAuthoritativeResultPayloadV1 = {
  readonly resultId: string;
  readonly contentHash: string;
  readonly capturePhotoId: string;
  readonly sessionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
};

export type StartServerProcessingPayloadV1 = {
  readonly sessionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly processingPlanVersion: string;
  readonly requestId: string;
};

export type ApplyLocalResultsPayloadV1 = {
  readonly sessionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly expectedResultIds: readonly string[];
};

export type FinalizeAislePayloadV1 = {
  readonly sessionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly finalizationId: string;
  readonly expectedAssetCount: number;
  readonly baseReadinessVersion: string;
};

export type CreateServerReprocessPayloadV1 = {
  readonly requestId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly scopeType: string;
  readonly scopeJson: string;
  readonly processingMode: string;
  readonly reason: string;
};

export type AdoptServerProposalsPayloadV1 = {
  readonly adoptionId: string;
  readonly runId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly contentHash: string;
  readonly decisionsJson: string;
};

export type SyncAisleRevisionPayloadV1 = {
  readonly revisionId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
};

export type ApplyAisleRevisionPayloadV1 = {
  readonly revisionId: string;
  readonly applyId: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly expectedBaseFinalizationId: string;
  readonly appliedBy: string;
};

export type OfflinePayloadV1 =
  | UploadAssetPayloadV1
  | SyncAuthoritativeResultPayloadV1
  | StartServerProcessingPayloadV1
  | ApplyLocalResultsPayloadV1
  | FinalizeAislePayloadV1
  | CreateServerReprocessPayloadV1
  | AdoptServerProposalsPayloadV1
  | SyncAisleRevisionPayloadV1
  | ApplyAisleRevisionPayloadV1;

function requireString(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  if (typeof v !== 'string' || !v.trim()) {
    throw new Error(`INVALID_PAYLOAD:${key}`);
  }
  return v;
}

function requireNumber(obj: Record<string, unknown>, key: string): number {
  const v = obj[key];
  if (typeof v !== 'number' || !Number.isFinite(v)) {
    throw new Error(`INVALID_PAYLOAD:${key}`);
  }
  return v;
}

function requireStringArray(obj: Record<string, unknown>, key: string): string[] {
  const v = obj[key];
  if (!Array.isArray(v) || !v.every((x) => typeof x === 'string')) {
    throw new Error(`INVALID_PAYLOAD:${key}`);
  }
  return v as string[];
}

export function encodePayload(payload: OfflinePayloadV1): string {
  return JSON.stringify(payload);
}

export function decodeUploadAssetPayloadV1(json: string): UploadAssetPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    localFilePath: requireString(obj, 'localFilePath'),
    assetId: requireString(obj, 'assetId'),
    capturePhotoId: requireString(obj, 'capturePhotoId'),
    sha256: requireString(obj, 'sha256'),
    preparedMimeType: requireString(obj, 'preparedMimeType'),
    byteSize: requireNumber(obj, 'byteSize'),
    sessionId: requireString(obj, 'sessionId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
  };
}

export function decodeSyncAuthoritativeResultPayloadV1(
  json: string,
): SyncAuthoritativeResultPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    resultId: requireString(obj, 'resultId'),
    contentHash: requireString(obj, 'contentHash'),
    capturePhotoId: requireString(obj, 'capturePhotoId'),
    sessionId: requireString(obj, 'sessionId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
  };
}

export function decodeStartServerProcessingPayloadV1(
  json: string,
): StartServerProcessingPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    sessionId: requireString(obj, 'sessionId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
    processingPlanVersion: requireString(obj, 'processingPlanVersion'),
    requestId: requireString(obj, 'requestId'),
  };
}

export function decodeApplyLocalResultsPayloadV1(json: string): ApplyLocalResultsPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    sessionId: requireString(obj, 'sessionId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
    expectedResultIds: requireStringArray(obj, 'expectedResultIds'),
  };
}

export function decodeFinalizeAislePayloadV1(json: string): FinalizeAislePayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    sessionId: requireString(obj, 'sessionId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
    finalizationId: requireString(obj, 'finalizationId'),
    expectedAssetCount: requireNumber(obj, 'expectedAssetCount'),
    baseReadinessVersion: requireString(obj, 'baseReadinessVersion'),
  };
}

export function decodeCreateServerReprocessPayloadV1(
  json: string,
): CreateServerReprocessPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    requestId: requireString(obj, 'requestId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
    scopeType: requireString(obj, 'scopeType'),
    scopeJson: requireString(obj, 'scopeJson'),
    processingMode: requireString(obj, 'processingMode'),
    reason: requireString(obj, 'reason'),
  };
}

export function decodeAdoptServerProposalsPayloadV1(
  json: string,
): AdoptServerProposalsPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    adoptionId: requireString(obj, 'adoptionId'),
    runId: requireString(obj, 'runId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
    contentHash: requireString(obj, 'contentHash'),
    decisionsJson: requireString(obj, 'decisionsJson'),
  };
}

export function decodeSyncAisleRevisionPayloadV1(json: string): SyncAisleRevisionPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    revisionId: requireString(obj, 'revisionId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
  };
}

export function decodeApplyAisleRevisionPayloadV1(json: string): ApplyAisleRevisionPayloadV1 {
  const obj = JSON.parse(json) as Record<string, unknown>;
  return {
    revisionId: requireString(obj, 'revisionId'),
    applyId: requireString(obj, 'applyId'),
    inventoryId: requireString(obj, 'inventoryId'),
    aisleId: requireString(obj, 'aisleId'),
    expectedBaseFinalizationId: requireString(obj, 'expectedBaseFinalizationId'),
    appliedBy: requireString(obj, 'appliedBy'),
  };
}

type PayloadDecoder = (json: string) => OfflinePayloadV1;

const REGISTRY: Record<string, PayloadDecoder> = {
  'UPLOAD_ASSET:1': decodeUploadAssetPayloadV1,
  'SYNC_AUTHORITATIVE_RESULT:1': decodeSyncAuthoritativeResultPayloadV1,
  'START_SERVER_PROCESSING:1': decodeStartServerProcessingPayloadV1,
  'APPLY_LOCAL_RESULTS:1': decodeApplyLocalResultsPayloadV1,
  'FINALIZE_AISLE:1': decodeFinalizeAislePayloadV1,
  'CREATE_SERVER_REPROCESS:1': decodeCreateServerReprocessPayloadV1,
  'ADOPT_SERVER_PROPOSALS:1': decodeAdoptServerProposalsPayloadV1,
  'SYNC_AISLE_REVISION:1': decodeSyncAisleRevisionPayloadV1,
  'APPLY_AISLE_REVISION:1': decodeApplyAisleRevisionPayloadV1,
};

export function decodePayloadForOperation(
  operationType: OfflineOperationType,
  payloadVersion: number,
  payloadJson: string,
): OfflinePayloadV1 {
  const key = `${operationType}:${payloadVersion}`;
  const decoder = REGISTRY[key];
  if (!decoder) {
    throw new Error('UNSUPPORTED_PAYLOAD_VERSION');
  }
  return decoder(payloadJson);
}
