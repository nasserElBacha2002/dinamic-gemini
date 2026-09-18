/**
 * Export prep path: when all photos READY, skip catch-up CODE_SCAN.
 */

import { LocalCsvExportService } from '../src/features/localCsv/localCsvExportService';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';

jest.mock('expo-file-system', () => {
  const published = new Set<string>();
  return {
    documentDirectory: 'file:///docs/',
    cacheDirectory: 'file:///cache/',
    EncodingType: { UTF8: 'utf8', Base64: 'base64' },
    getInfoAsync: jest.fn(async (uri: string) => {
      const u = String(uri);
      if (u.includes('staging') || u.includes('photo')) {
        return { exists: true, size: 4 };
      }
      if (published.has(u)) {
        return { exists: true, size: 100 };
      }
      if (u.endsWith('.csv') || u.endsWith('.zip') || u.includes('.tmp.')) {
        return { exists: false };
      }
      return { exists: true, size: 4 };
    }),
    makeDirectoryAsync: jest.fn(async () => undefined),
    writeAsStringAsync: jest.fn(async () => undefined),
    moveAsync: jest.fn(async ({ from, to }: { from: string; to: string }) => {
      published.delete(String(from));
      published.add(String(to));
    }),
    deleteAsync: jest.fn(async (uri: string) => {
      published.delete(String(uri));
    }),
    readAsStringAsync: jest.fn(async () => 'AAAA'),
    copyAsync: jest.fn(async () => undefined),
  };
});

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn(async () => false),
  shareAsync: jest.fn(async () => undefined),
}));

jest.mock('../src/features/localCodeScan/preparedAssetHash', () => ({
  hashPreparedFileSha256: jest.fn(async () => 'deadbeef'),
  hashPreparedMetaSha256: jest.fn(() => 'meta'),
}));

jest.mock('../src/features/localCsv/binaryCodec', () => ({
  base64ToUint8Array: jest.fn(() => new Uint8Array([0xff, 0xd8, 0xff, 0xd9])),
  uint8ArrayToBase64: jest.fn(() => 'AAAA'),
}));

jest.mock('../src/core/payloadFingerprint', () => {
  const actual = jest.requireActual('../src/core/payloadFingerprint') as Record<string, unknown>;
  return {
    ...actual,
    sha256BytesHex: jest.fn(
      () => 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    ),
  };
});

jest.mock('../src/features/exportPrep/validateReadyStaging', () => ({
  validateReadyStaging: jest.fn(async () => ({
    ok: true,
    digest: {
      sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      bytesHashed: 4,
      hashMode: 'native_file',
      hashSource: 'computed',
      durationMs: 1,
      reason: null,
    },
  })),
  isConfirmedReadyIntegrityFailure: jest.fn(() => false),
}));

jest.mock('../src/features/exportPrep/streamingZipWriter', () => ({
  writeStoreZipAtomic: jest.fn(async () => ({
    byteLength: 10,
    sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    entryCount: 3,
    method: 'STORE',
    peakOpenEntries: 1,
    physicalPath: '/tmp/mock-export.zip',
  })),
  buildStoreZipBytes: jest.fn(),
}));

jest.mock('../src/features/exportPrep/boundedOnDiskZipValidator', () => ({
  validateOnDiskStoreZip: jest.fn(async () => ({
    ok: true,
    entryCount: 3,
    entries: [],
    zipSizeBytes: 10,
    zipSha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    manifest: {
      package_kind: 'DINAMIC_LOCAL_AISLE_EXPORT',
      package_version: 2,
      included_photo_count: 1,
      expected_photo_count: 1,
    },
    rangeReads: 2,
    maxBufferBytes: 64,
  })),
}));

describe('LocalCsvExportService export prep skip-scan', () => {
  const now = '2026-01-01T00:00:00.000Z';

  function session(): CaptureSessionRow {
    return {
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-1',
      aisle_name: 'A1',
      status: 'local_completed',
      started_at: now,
      finished_at: now,
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
      upload_batch_id: null,
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
      size: 4,
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
      upload_batch_id: null,
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

  it('skips ensureLocalCodeScans when all eligible jobs are READY', async () => {
    const execute = jest.fn(async () => 'RESOLVED' as const);
    const drafts = [
      {
        id: 'd1',
        capture_photo_id: 'session-1:1',
        capture_session_id: 'session-1',
        status: 'RESOLVED',
        internal_code: 'SKU-1',
        label_id: 'L1',
        product_results_json: null,
        recognition_profile_snapshot_json: null,
        position_detected: 0,
        error_code: null,
        rejections_json: null,
      },
    ];
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
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
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
        markShared: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      exportPrepRepo: {
        listForSession: jest.fn(async () => [
          {
            capture_photo_id: 'session-1:1',
            capture_session_id: 'session-1',
            status: 'READY',
            source_uri: 'file://photo.jpg',
            staging_uri: 'file:///docs/export-staging/session-1/photos/0001_session-1_1.jpg',
            export_file_name: '0001_session-1_1.jpg',
            size_bytes: 4,
            sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            source_fingerprint: null,
            error_code: null,
            error_message: null,
            attempt_count: 1,
            max_attempts: 3,
            lease_token: null,
            lease_expires_at: null,
            queued_at: now,
            started_at: now,
            ready_at: now,
            updated_at: now,
            created_at: now,
          },
        ]),
        invalidateReady: jest.fn(async () => undefined),
      } as never,
    });

    const result = await svc.exportSession('session-1');
    expect(execute).not.toHaveBeenCalled();
    expect(result.scanMode).toBe('skipped_all_ready');
    expect(result.photoCount).toBe(1);
  });

  it('blocks export when a prep job is still QUEUED', async () => {
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: { listForSession: jest.fn(async () => []) } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      exportPrepRepo: {
        listForSession: jest.fn(async () => [
          {
            capture_photo_id: 'session-1:1',
            status: 'QUEUED',
            staging_uri: null,
            export_file_name: null,
            size_bytes: null,
            sha256: null,
          },
        ]),
      } as never,
    });
    await expect(svc.exportSession('session-1')).rejects.toThrow(/PACKAGE_EXPORT_PREP_PENDING/);
  });
});
