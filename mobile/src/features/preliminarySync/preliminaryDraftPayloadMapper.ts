import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import { normalizeLocalPositionCode } from '../../core/positionLabelPayload';
import type {
  PositionSyncReferenceV2,
  PreliminaryDetectionSyncRequest,
} from './preliminaryDetectionApi';

export function mapDraftToPreliminarySyncRequest(input: {
  readonly draft: LocalDetectionDraftRow;
  readonly assetId: string;
  readonly positionReferenceV2Enabled?: boolean;
}): PreliminaryDetectionSyncRequest {
  const { draft, assetId } = input;
  const positionReference = input.positionReferenceV2Enabled
    ? parsePositionReference(draft.position_snapshot_json)
    : null;
  const base: PreliminaryDetectionSyncRequest = {
    schema_version: positionReference ? '2' : '1',
    capture_session_id: draft.capture_session_id,
    capture_photo_id: draft.capture_photo_id,
    client_file_id: draft.client_file_id!,
    asset_id: assetId,
    processing_mode: 'CODE_SCAN',
    status: draft.status,
    internal_code: draft.internal_code,
    quantity: draft.quantity,
    quantity_status: draft.quantity_status,
    detected_format: draft.detected_format,
    detected_symbology: draft.detected_symbology,
    candidate_count: draft.candidate_count,
    parser_version: draft.parser_version,
    detector_version: draft.detector_version,
    prepared_asset_sha256: draft.prepared_asset_fingerprint!,
    payload_hash: draft.raw_value_hash,
    processing_ms: draft.processing_ms,
    detected_at: draft.detected_at,
  };
  return positionReference ? { ...base, position_reference: positionReference } : base;
}

function parsePositionReference(json: string | null): PositionSyncReferenceV2 | null {
  if (!json?.trim()) return null;
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    return null;
  }
  if (!isRecord(value) || value.schemaVersion !== 2 || value.payloadVersion !== 2) {
    return null;
  }
  const signature = isRecord(value.signatureEvidence)
    ? value.signatureEvidence
    : null;
  const verification = signature?.verification;
  if (
    !signature ||
    typeof signature.present !== 'boolean' ||
    (verification !== 'MISSING' &&
      verification !== 'UNVERIFIED' &&
      verification !== 'INVALID' &&
      verification !== 'NOT_APPLICABLE')
  ) {
    return null;
  }
  const localRecognitionId = requiredText(value.localRecognitionId);
  const rawCode = exactText(value.rawCode);
  const normalizedCode = canonicalPositionCode(value.normalizedCode);
  const source = requiredText(value.source);
  const capturedAt = requiredText(value.capturedAt);
  if (!localRecognitionId || !rawCode || !normalizedCode || !source || !capturedAt) {
    return null;
  }
  return {
    payload_version: 2,
    local_recognition_id: localRecognitionId,
    raw_code: rawCode,
    normalized_code: normalizedCode,
    remote_position_id: optionalText(value.remotePositionId),
    remote_position_label_id: optionalText(value.remotePositionLabelId),
    source,
    profile_id: optionalText(value.profileId),
    profile_version:
      typeof value.profileVersion === 'number' && Number.isInteger(value.profileVersion)
        ? value.profileVersion
        : null,
    client_supplier_id: optionalText(value.clientSupplierId),
    signature: { present: signature.present, verification },
    captured_at: capturedAt,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function exactText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function optionalText(value: unknown): string | null {
  return value == null ? null : requiredText(value);
}

function canonicalPositionCode(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    return normalizeLocalPositionCode(value);
  } catch {
    return null;
  }
}
