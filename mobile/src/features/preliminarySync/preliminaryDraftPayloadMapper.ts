import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import type { PreliminaryDetectionSyncRequest } from './preliminaryDetectionApi';

export function mapDraftToPreliminarySyncRequest(input: {
  readonly draft: LocalDetectionDraftRow;
  readonly assetId: string;
}): PreliminaryDetectionSyncRequest {
  const { draft, assetId } = input;
  return {
    schema_version: '1',
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
}
