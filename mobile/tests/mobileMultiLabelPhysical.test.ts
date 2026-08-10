/**
 * Physical multi-label local CODE_SCAN regression fixtures (CSV + position raw).
 */

import { describe, expect, it, beforeEach } from '@jest/globals';
import {
  applyPositionScan,
  clearAllActivePositions,
  getActivePosition,
} from '../src/features/localCodeScan/activePositionStore';
import { buildLocalCsvRows } from '../src/features/localCsv/buildLocalCsvExport';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { LocalDetectionDraftRow } from '../src/database/repositories/localDetectionDraftRepository';
import {
  classifyDinamicPositionPayload,
  parseDinamicPositionPayload,
} from '../src/core/positionLabelPayload';
import { consolidateCodeDetections } from '../src/core/codeDetectionConsolidator';

/** Minimal valid-looking D1 vectors — tests mock via raw strings already used in suite. */
function makeSession(): CaptureSessionRow {
  return {
    id: 'sess-1',
    inventory_id: 'inv-1',
    inventory_name: 'Inv',
    aisle_id: 'aisle-1',
    aisle_name: 'A1',
    status: 'active',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
  } as CaptureSessionRow;
}

function makePhoto(id: string, order: number): CapturePhotoRow {
  return {
    id,
    capture_session_id: 'sess-1',
    asset_id: `asset-${id}`,
    status: 'ready',
    sequence_number: order,
    date_added: order,
    created_at: '2026-08-10T00:00:00Z',
    client_file_id: `cf-${id}`,
  } as unknown as CapturePhotoRow;
}

function makeDraft(
  photoId: string,
  overrides: Partial<LocalDetectionDraftRow>,
): LocalDetectionDraftRow {
  return {
    id: `draft-${photoId}`,
    capture_photo_id: photoId,
    capture_session_id: 'sess-1',
    client_file_id: `cf-${photoId}`,
    status: 'RESOLVED',
    raw_value_hash: null,
    internal_code: null,
    quantity: null,
    quantity_status: null,
    detected_format: null,
    detected_symbology: null,
    parser_version: '1',
    detector_version: '1',
    candidate_count: 1,
    error_code: null,
    processing_ms: 1,
    comparison_status: 'PENDING',
    compare_result: null,
    compared_at: null,
    prepared_asset_fingerprint: 'fp',
    scan_owner: null,
    scan_generation: 1,
    sync_status: 'NOT_READY',
    sync_attempt_count: 0,
    sync_next_retry_at: null,
    sync_last_error_code: null,
    server_preliminary_id: null,
    synced_at: null,
    sync_lease_token: null,
    sync_lease_expires_at: null,
    position_snapshot_json: null,
    label_id: null,
    product_results_json: null,
    position_detected: 0,
    detected_at: '2026-08-10T00:00:00Z',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    ...overrides,
  };
}

describe('mobile multi-label physical corrections', () => {
  beforeEach(() => {
    clearAllActivePositions();
  });

  it('photo 6: two D1 products → two CSV rows with label_id and shared position snapshot', () => {
    const positionState = {
      labelId: 'pos_04',
      positionLabelId: 'pos_04',
      displayName: '04 RIGHT N1 02/02',
      canonicalKey: '04|RIGHT|1|2|2',
      pallet: '04',
      side: 'RIGHT' as const,
      level: 1,
      markerIndex: 2,
      markerTotal: 2,
      formattedMarker: '02/02',
      rawPayload:
        '{"key_version":1,"label_id":"pos_04","level":1,"marker_index":2,"marker_total":2,"pallet":"04","side":"RIGHT","signature":"abc","type":"DINAMIC_POSITION","version":2}',
      sourcePayload:
        '{"key_version":1,"label_id":"pos_04","level":1,"marker_index":2,"marker_total":2,"pallet":"04","side":"RIGHT","signature":"abc","type":"DINAMIC_POSITION","version":2}',
      validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED' as const,
      signature: 'abc',
      keyVersion: 1,
    };
    const draft = makeDraft('photo-6', {
      internal_code: '232424090',
      quantity: 1000,
      label_id: '6YD0S6WVMM',
      product_results_json: JSON.stringify([
        {
          labelId: '6YD0S6WVMM',
          internalCode: '232424090',
          quantity: 1000,
          validationStatus: 'VALID',
        },
        {
          labelId: '6FYR11RPXS',
          internalCode: '232424025',
          quantity: 1100,
          validationStatus: 'VALID',
        },
      ]),
      position_snapshot_json: JSON.stringify(positionState),
      position_detected: 0,
    });
    const rows = buildLocalCsvRows({
      session: makeSession(),
      photos: [makePhoto('photo-6', 6)],
      drafts: [draft],
      confirmed: [],
      deviceId: 'dev',
      companyId: null,
      clientId: 'client',
    });
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.internal_code)).toEqual(['232424090', '232424025']);
    expect(rows.map((r) => r.label_id)).toEqual(['6YD0S6WVMM', '6FYR11RPXS']);
    expect(rows.map((r) => r.quantity)).toEqual(['1000', '1100']);
    expect(rows.every((r) => r.capture_photo_id === 'photo-6')).toBe(true);
    expect(rows.every((r) => r.position_status === 'FROM_SNAPSHOT')).toBe(true);
    expect(rows[0]!.position_payload_raw).toContain('"signature":"abc"');
    expect(rows[0]!.position_payload_raw).toContain('"key_version":1');
  });

  it('same photo POSITION + PRODUCT → LABEL_DETECTED not FROM_SNAPSHOT', () => {
    const rawPos =
      '{"label_id":"pos_mix","level":1,"marker_index":1,"marker_total":1,"pallet":"02","side":"LEFT","type":"DINAMIC_POSITION","version":2}';
    applyPositionScan('sess-1', rawPos);
    const active = getActivePosition('sess-1')!;
    const draft = makeDraft('photo-3', {
      product_results_json: JSON.stringify([
        {
          labelId: 'LABEL-P',
          internalCode: 'SKU-P',
          quantity: 5,
          validationStatus: 'VALID',
        },
      ]),
      label_id: 'LABEL-P',
      internal_code: 'SKU-P',
      quantity: 5,
      position_detected: 1,
      position_snapshot_json: JSON.stringify(active),
      error_code: null,
    });
    const rows = buildLocalCsvRows({
      session: makeSession(),
      photos: [makePhoto('photo-3', 3)],
      drafts: [draft],
      confirmed: [],
      deviceId: 'dev',
      companyId: null,
      clientId: 'client',
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]!.source).toBe('LOCAL_CODE_SCAN');
    expect(rows[0]!.position_status).toBe('LABEL_DETECTED');
    expect(rows[0]!.label_id).toBe('LABEL-P');
    expect(rows[0]!.position_payload_raw).toBe(rawPos);
  });

  it('preserves exact position raw including signature (no reserialize subset)', () => {
    const raw =
      '{"key_version":1,"label_id":"pos_x","level":1,"marker_index":1,"marker_total":1,"pallet":"01","side":"LEFT","signature":"deadbeef","type":"DINAMIC_POSITION","version":2}';
    expect(classifyDinamicPositionPayload(raw)).toBe('STRUCTURALLY_VALID_UNVERIFIED');
    const parsed = parseDinamicPositionPayload(raw);
    expect(parsed?.signature).toBe('deadbeef');
    expect(parsed?.keyVersion).toBe(1);
    const state = applyPositionScan('sess-raw', raw)!;
    expect(state.rawPayload).toBe(raw);
    expect(state.signature).toBe('deadbeef');
  });

  it('consolidator keeps positionRawPayload on position-only photo', () => {
    const posRaw =
      '{"label_id":"pos_co","level":1,"marker_index":1,"marker_total":1,"pallet":"09","side":"LEFT","type":"DINAMIC_POSITION","version":2}';
    const result = consolidateCodeDetections([
      { rawValue: posRaw, symbology: 'QR_CODE', detectionIndex: 0 },
    ]);
    expect(result.positionRawPayload).toBe(posRaw);
    expect(result.warnings).toContain('POSITION_LABEL_DETECTED');
    expect(result.productResults).toHaveLength(0);
  });
});
