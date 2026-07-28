/**
 * Phase 9 — canonical payload hash for idempotency conflict detection.
 */

import { sha256Hex } from '../../core/payloadFingerprint';
import type { OfflineOperationType } from './offlineOperationTypes';

export function canonicalizeOfflinePayload(input: {
  readonly operationType: OfflineOperationType;
  readonly entityType: string;
  readonly entityId: string;
  readonly payloadVersion: number;
  readonly payloadJson: string;
  readonly dependsOnOperationIds?: readonly string[];
}): string {
  let payloadObj: unknown = input.payloadJson;
  try {
    payloadObj = JSON.parse(input.payloadJson) as unknown;
  } catch {
    // keep raw string
  }
  const deps = [...(input.dependsOnOperationIds ?? [])].sort();
  return JSON.stringify({
    type: input.operationType,
    entityType: input.entityType,
    entityId: input.entityId,
    payloadVersion: input.payloadVersion,
    payload: payloadObj,
    dependencies: deps,
  });
}

export function computeOfflinePayloadHash(input: {
  readonly operationType: OfflineOperationType;
  readonly entityType: string;
  readonly entityId: string;
  readonly payloadVersion: number;
  readonly payloadJson: string;
  readonly dependsOnOperationIds?: readonly string[];
}): string {
  return sha256Hex(canonicalizeOfflinePayload(input));
}
