/**
 * Local ZIP export must run CODE_SCAN before readiness assert when upload is deferred.
 */

import { LocalCsvExportService } from '../src/features/localCsv/localCsvExportService';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  cacheDirectory: 'file:///cache/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async () => ({ exists: false })),
  makeDirectoryAsync: jest.fn(async () => undefined),
  writeAsStringAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => 'aaaa'),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn(async () => false),
  shareAsync: jest.fn(async () => undefined),
}));

jest.mock('fflate', () => ({
  zipSync: jest.fn(() => new Uint8Array([1, 2, 3, 4])),
}));

jest.mock('../src/features/localCodeScan/preparedAssetHash', () => ({
  hashPreparedFileSha256: jest.fn(async () => 'sha256:prepared'),
  hashPreparedMetaSha256: jest.fn(() => 'sha256:meta'),
}));

jest.mock('../src/features/localCsv/binaryCodec', () => ({
  base64ToUint8Array: jest.fn(() => new Uint8Array([0xff, 0xd8, 0xff, 0xd9])),
  uint8ArrayToBase64: jest.fn(() => 'AAAA'),
}));

describe('LocalCsvExportService CODE_SCAN before export', () => {
  const now = '2026-01-01T00:00:00.000Z';

  function session(): CaptureSessionRow {
    return {
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-1',
      aisle_name: 'A1',
      status: 'review',
      started_at: now,
      finished_at: null,
      initial_asset_id: null,
      initial_date_added: null,
      initial_date_modified: null,
      initial_display_name: null,
      initial_size: null,
      initial_bucket_id: null,
      scan_cursor_date_added: EMPTY_CURSOR.dateAdded,
      scan_cursor_asset_id: EMPTY_CURSOR.assetId,
      last_valid_cursor_date_added: EMPTY_CURSOR.dateAdded,
      last_valid_cursor_asset_id: EMPTY_CURSOR.assetId,
      upload_batch_id: 'b1',
      upload_status: 'idle',
      processing_status: 'idle',
      backend_job_id: null,
      upload_started_at: null,
      upload_completed_at: null,
      processing_started_at: null,
      processing_finished_at: null,
      last_upload_error: null,
      last_processing_error: null,
      preparation_processing_mode: 'CODE_SCAN',
      backend_ordered_capture_session_id: null,
      process_attempt_id: null,
      process_idempotency_key: null,
      process_requested_at: null,
      process_confirmed_at: null,
      last_recovery_check_at: null,
      capture_frozen_at: now,
      capture_frozen_photo_count: 1,
      capture_freeze_generation: 1,
      active_freeze_id: null,
      upload_policy: 'MANUAL',
      created_at: now,
      updated_at: now,
    } as CaptureSessionRow;
  }

  function photo(): CapturePhotoRow {
    return {
      id: 'session-1:1',
      capture_session_id: 'session-1',
      asset_id: '1',
      media_store_numeric_id: 1,
      uri: 'file://photo.jpg',
      display_name: 'photo.jpg',
      mime_type: 'image/jpeg',
      size: 10,
      width: 1,
      height: 1,
      date_added: 1,
      date_modified: 1,
      bucket_id: null,
      relative_path: null,
      status: 'stable',
      rejection_reason: null,
      stability_checks: 1,
      stability_attempts: 1,
      stability_error: null,
      last_stability_attempt_at: null,
      detected_at: now,
      stable_at: now,
      excluded_at: null,
      client_file_id: 'cf-1',
      sequence_number: 1,
      backend_asset_id: null,
      upload_status: 'not_queued',
      upload_progress: 0,
      upload_attempts: 0,
      upload_batch_id: 'b1',
      last_upload_error_code: null,
      last_upload_error_message: null,
      last_upload_attempt_at: null,
      next_retry_at: null,
      uploaded_at: null,
      remote_deleted_at: null,
      local_transform_uri: null,
      original_size: null,
      upload_size: null,
      upload_worker_owner: null,
      upload_lease_token: null,
      upload_lease_expires_at: null,
      upload_heartbeat_at: null,
      upload_cancel_requested: 0,
      created_at: now,
      updated_at: now,
    } as CapturePhotoRow;
  }

  it('runs local CODE_SCAN with session context before building export rows', async () => {
    const execute = jest.fn(async () => 'RESOLVED' as const);
    const drafts: unknown[] = [];
    const sess = session();
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => sess),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => drafts as never),
      } as never,
      confirmedRepo: {
        listForSession: jest.fn(async () => []),
      } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        insert: jest.fn(async () => undefined),
        markShared: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute } as never,
      localCodeScanEnabled: true,
    });

    execute.mockImplementation(async () => {
      drafts.push({
        id: 'd1',
        capture_photo_id: 'session-1:1',
        capture_session_id: 'session-1',
        client_file_id: 'cf-1',
        status: 'RESOLVED',
        raw_value_hash: null,
        internal_code: 'SKU-1',
        quantity: 2,
        quantity_status: 'PRESENT',
        detected_format: 'PLAIN',
        detected_symbology: 'QR_CODE',
        parser_version: '1',
        detector_version: '1',
        candidate_count: 1,
        error_code: null,
        processing_ms: 1,
        comparison_status: null,
        compare_result: null,
        compared_at: null,
        prepared_asset_fingerprint: 'sha256:prepared',
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
        detected_at: now,
        created_at: now,
        updated_at: now,
      });
      return 'RESOLVED';
    });

    const result = await svc.exportSession('session-1');
    expect(execute).toHaveBeenCalledWith(
      expect.objectContaining({
        inventoryId: 'inv-1',
        aisleId: 'aisle-1',
        recognitionContext: 'OFFLINE',
        processingMode: 'CODE_SCAN',
      }),
    );
    expect(result.rowCount).toBe(1);
    expect(result.zipUri).toContain('.zip');
  });

  it('skips rescan when draft is already export-ready', async () => {
    const execute = jest.fn(async () => 'RESOLVED' as const);
    const readyDraft = {
      id: 'd-ready',
      capture_photo_id: 'session-1:1',
      capture_session_id: 'session-1',
      client_file_id: 'cf-1',
      status: 'RESOLVED',
      internal_code: 'SKU-READY',
      product_results_json: JSON.stringify([
        { labelId: 'L1', internalCode: 'SKU-READY', quantity: 3 },
      ]),
      recognition_profile_snapshot_json: null,
      position_detected: 0,
      error_code: null,
    };
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => [readyDraft]),
      } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        insert: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute } as never,
      localCodeScanEnabled: true,
    });

    await svc.exportSession('session-1');
    expect(execute).not.toHaveBeenCalled();
  });
});
