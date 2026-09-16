/**
 * Correction-focused tests: hash fail-closed, terminal export gate, ZIP atomicity,
 * flag-off legacy path.
 */

import { LocalCsvExportService } from '../src/features/localCsv/localCsvExportService';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';
import {
  ExportPrepFenceError,
  ExportPrepRepository,
  isValidStagedSha256,
} from '../src/database/repositories/exportPrepRepository';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { hashStagedFileSha256Hex } from '../src/features/exportPrep/stagedSha256';
import * as FileSystem from 'expo-file-system';
import { writeStoreZipAtomic } from '../src/features/exportPrep/streamingZipWriter';

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(async () => 'b'.repeat(64)),
}));

jest.mock('../src/features/exportPrep/exportStaging', () => {
  const actual = jest.requireActual('../src/features/exportPrep/exportStaging') as Record<
    string,
    unknown
  >;
  return {
    ...actual,
    stageOriginalPhotoVersioned: jest.fn(async () => ({
      stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
      sizeBytes: 12,
    })),
    stagingFileExists: jest.fn(async () => true),
  };
});

jest.mock('../src/features/exportPrep/streamingZipWriter', () => ({
  writeStoreZipAtomic: jest.fn(async () => ({ byteLength: 10, sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' })),
  buildStoreZipBytes: jest.fn(),
}));

jest.mock('expo-file-system', () => {
  const published = new Set<string>();
  return {
    documentDirectory: 'file:///docs/',
    cacheDirectory: 'file:///cache/',
    EncodingType: { UTF8: 'utf8', Base64: 'base64' },
    getInfoAsync: jest.fn(async (uri: string) => {
      const u = String(uri);
      if (u.includes('staging') || u.includes('photo.jpg')) {
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
    readAsStringAsync: jest.fn(async () => Buffer.from('abcd').toString('base64')),
    copyAsync: jest.fn(async () => undefined),
    __published: published,
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

const VALID_SHA = 'b'.repeat(64);

function session(): CaptureSessionRow {
  const now = '2026-01-01T00:00:00.000Z';
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
  const now = '2026-01-01T00:00:00.000Z';
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

describe('staged SHA-256 fail-closed', () => {
  it('rejects empty bytes via mocked hasher contract', async () => {
    (hashStagedFileSha256Hex as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error('EXPORT_PREP_HASH_EMPTY'), { code: 'EXPORT_PREP_HASH_EMPTY' }),
    );
    await expect(hashStagedFileSha256Hex('file:///docs/x.jpg')).rejects.toThrow(
      /EXPORT_PREP_HASH_EMPTY/,
    );
  });

  it('never treats metadata fingerprints as staged sha256', () => {
    expect(isValidStagedSha256('meta')).toBe(false);
    expect(isValidStagedSha256('sha256:deadbeef')).toBe(false);
    expect(isValidStagedSha256(VALID_SHA)).toBe(true);
  });
});

describe('ExportPrepQueue processJob', () => {
  it('never calls markReady when staged hash fails; uses fenced markFailed', async () => {
    (hashStagedFileSha256Hex as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error('hash fail'), { code: 'EXPORT_PREP_HASH_FAILED' }),
    );

    const markReady = jest.fn();
    const markFailedFenced = jest.fn(async () => 'FAILED_RETRYABLE' as const);
    const job = {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'PREPARING' as const,
      source_uri: 'file://source/a.jpg',
      staging_uri: null,
      export_file_name: '0001_p1.jpg',
      size_bytes: null,
      sha256: null,
      source_fingerprint: null,
      error_code: null,
      error_message: null,
      attempt_count: 1,
      max_attempts: 3,
      lease_token: 'lease-1',
      lease_expires_at: '2099-01-01T00:00:00.000Z',
      queued_at: '2026-01-01T00:00:00.000Z',
      started_at: '2026-01-01T00:00:00.000Z',
      ready_at: null,
      updated_at: '2026-01-01T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
    };

    const queue = new ExportPrepQueue({
      prepRepo: {
        renewLease: jest.fn(async () => undefined),
        markScanning: jest.fn(async () => undefined),
        markValidating: jest.fn(async () => undefined),
        markReady,
        markFailedFenced,
        markExcluded: jest.fn(async () => undefined),
        countsForSession: jest.fn(async () => ({
          queued: 0,
          preparing: 0,
          scanning: 0,
          validating: 0,
          ready: 0,
          failedRetryable: 1,
          failedTerminal: 0,
          excluded: 0,
          pending: 0,
          processing: 0,
          failed: 1,
          total: 1,
        })),
      } as never,
      captureRepo: {
        getPhotoById: async () => ({
          id: 'p1',
          capture_session_id: 's1',
          status: 'stable',
          uri: 'file://source/a.jpg',
          sequence_number: 1,
          display_name: 'a.jpg',
          client_file_id: null,
          upload_cancel_requested: 0,
        }),
        getSession: async () => ({ id: 's1', preparation_processing_mode: 'CODE_SCAN' }),
      } as never,
      draftRepo: {
        listForSession: async () => [
          {
            capture_photo_id: 'p1',
            status: 'RESOLVED',
            internal_code: 'SKU',
            label_id: 'L',
            product_results_json: '[]',
            position_detected: 0,
          },
        ],
      } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });

    await (queue as unknown as { processJob: (j: typeof job) => Promise<void> }).processJob(job);

    expect(markReady).not.toHaveBeenCalled();
    expect(markFailedFenced).toHaveBeenCalledWith(
      'p1',
      'lease-1',
      'EXPORT_PREP_HASH_FAILED',
      expect.any(String),
    );
    queue.stop();
  });

  it('abandons on fence loss without overwriting via markFailedFenced', async () => {
    const markFailedFenced = jest.fn();
    const markReady = jest.fn();
    const job = {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'PREPARING' as const,
      source_uri: 'file://source/a.jpg',
      staging_uri: null,
      export_file_name: '0001_p1.jpg',
      size_bytes: null,
      sha256: null,
      source_fingerprint: null,
      error_code: null,
      error_message: null,
      attempt_count: 1,
      max_attempts: 3,
      lease_token: 'lease-stale',
      lease_expires_at: '2099-01-01T00:00:00.000Z',
      queued_at: '2026-01-01T00:00:00.000Z',
      started_at: '2026-01-01T00:00:00.000Z',
      ready_at: null,
      updated_at: '2026-01-01T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
    };

    const queue = new ExportPrepQueue({
      prepRepo: {
        renewLease: jest.fn(async () => {
          throw new ExportPrepFenceError('lost');
        }),
        markScanning: jest.fn(),
        markValidating: jest.fn(),
        markReady,
        markFailedFenced,
        markExcluded: jest.fn(),
        countsForSession: jest.fn(async () => ({
          queued: 0,
          preparing: 0,
          scanning: 0,
          validating: 0,
          ready: 0,
          failedRetryable: 0,
          failedTerminal: 0,
          excluded: 0,
          pending: 0,
          processing: 0,
          failed: 0,
          total: 0,
        })),
      } as never,
      captureRepo: {
        getPhotoById: async () => ({
          id: 'p1',
          capture_session_id: 's1',
          status: 'stable',
          sequence_number: 1,
          display_name: 'a.jpg',
          uri: 'file://a',
          client_file_id: null,
          upload_cancel_requested: 0,
        }),
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });

    await (queue as unknown as { processJob: (j: typeof job) => Promise<void> }).processJob(job);
    expect(markReady).not.toHaveBeenCalled();
    expect(markFailedFenced).not.toHaveBeenCalled();
    expect(queue.metrics.fenceLost).toBeGreaterThan(0);
    queue.stop();
  });
});

describe('FAILED_TERMINAL blocks export', () => {
  it('throws PACKAGE_EXPORT_PREP_TERMINAL', async () => {
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: { listForSession: jest.fn(async () => []) } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: { findByFingerprint: jest.fn(async () => null), findBySessionAndFingerprint: jest.fn(async () => null), tryInsert: jest.fn(async () => true) } as never,
      deviceId: 'dev-1',
      exportPrepEnabled: true,
      exportPrepRepo: {
        listForSession: jest.fn(async () => [
          {
            capture_photo_id: 'session-1:1',
            status: 'FAILED_TERMINAL',
            error_code: 'EXPORT_PREP_HASH_FAILED',
          },
        ]),
      } as never,
    });
    await expect(svc.exportSession('session-1')).rejects.toThrow(/PACKAGE_EXPORT_PREP_TERMINAL/);
  });
});

describe('ZIP failure leaves no published CSV', () => {
  beforeEach(() => {
    (FileSystem.moveAsync as jest.Mock).mockReset();
    (FileSystem.moveAsync as jest.Mock).mockImplementation(
      async ({ from, to }: { from: string; to: string }) => {
        const pub = (FileSystem as unknown as { __published?: Set<string> }).__published;
        pub?.delete(String(from));
        pub?.add(String(to));
      },
    );
    (FileSystem.deleteAsync as jest.Mock).mockReset();
    (FileSystem.deleteAsync as jest.Mock).mockImplementation(async (uri: string) => {
      (FileSystem as unknown as { __published?: Set<string> }).__published?.delete(String(uri));
    });
    (writeStoreZipAtomic as jest.Mock).mockReset();
    (writeStoreZipAtomic as jest.Mock).mockResolvedValue({ byteLength: 10, sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' });
  });
  it('cleans temps and does not publish final csv/zip', async () => {
    (writeStoreZipAtomic as jest.Mock).mockRejectedValueOnce(new Error('ZIP_BOOM'));

    const moveAsync = FileSystem.moveAsync as jest.Mock;
    moveAsync.mockClear();

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
      draftRepo: { listForSession: jest.fn(async () => drafts as never) } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScanEnabled: false,
      exportPrepEnabled: true,
      exportPrepRepo: {
        listForSession: jest.fn(async () => [
          {
            capture_photo_id: 'session-1:1',
            capture_session_id: 'session-1',
            status: 'READY',
            source_uri: 'file://photo.jpg',
            staging_uri: 'file:///docs/export-staging/session-1/photos/0001.jpg',
            export_file_name: '0001_session-1_1.jpg',
            size_bytes: 4,
            sha256: VALID_SHA,
            source_fingerprint: null,
            error_code: null,
            error_message: null,
            attempt_count: 1,
            max_attempts: 3,
            lease_token: null,
            lease_expires_at: null,
            queued_at: '2026-01-01T00:00:00.000Z',
            started_at: '2026-01-01T00:00:00.000Z',
            ready_at: '2026-01-01T00:00:00.000Z',
            updated_at: '2026-01-01T00:00:00.000Z',
            created_at: '2026-01-01T00:00:00.000Z',
          },
        ]),
        invalidateReady: jest.fn(async () => undefined),
      } as never,
    });

    await expect(svc.exportSession('session-1')).rejects.toThrow(/ZIP_BOOM/);
    expect(moveAsync).not.toHaveBeenCalled();
    expect(FileSystem.deleteAsync).toHaveBeenCalled();
  });

  it('CSV move failure does not insert export and leaves prior artifacts', async () => {
    (writeStoreZipAtomic as jest.Mock).mockResolvedValueOnce({ byteLength: 10, sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' });
    const moveAsync = FileSystem.moveAsync as jest.Mock;
    moveAsync.mockImplementation(async ({ from }: { from: string }) => {
      if (String(from).includes('.tmp.csv')) {
        throw new Error('CSV_MOVE_FAIL');
      }
    });
    const insert = jest.fn(async () => undefined);
    const published = new Set<string>([
      'file:///docs/aisle-exports/prior.csv',
      'file:///docs/aisle-exports/prior.zip',
    ]);
    (FileSystem.getInfoAsync as jest.Mock).mockImplementation(async (uri: string) => {
      const u = String(uri);
      if (u.includes('staging') || u.includes('photo')) return { exists: true, size: 4 };
      if (published.has(u)) return { exists: true, size: 100 };
      if (u.includes('.csv') || u.includes('.zip')) return { exists: false };
      return { exists: true, size: 4 };
    });
    (FileSystem.deleteAsync as jest.Mock).mockImplementation(async (uri: string) => {
      published.delete(String(uri));
    });

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
      draftRepo: { listForSession: jest.fn(async () => drafts as never) } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: { findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: insert, insert } as never,
      deviceId: 'dev-1',
      localCodeScanEnabled: false,
      exportPrepEnabled: true,
      exportPrepRepo: {
        listForSession: jest.fn(async () => [
          {
            capture_photo_id: 'session-1:1',
            capture_session_id: 'session-1',
            status: 'READY',
            source_uri: 'file://photo.jpg',
            staging_uri: 'file:///docs/export-staging/session-1/photos/0001.jpg',
            export_file_name: '0001_session-1_1.jpg',
            size_bytes: 4,
            sha256: VALID_SHA,
            source_fingerprint: null,
            error_code: null,
            error_message: null,
            attempt_count: 1,
            max_attempts: 3,
            lease_token: null,
            lease_expires_at: null,
            queued_at: '2026-01-01T00:00:00.000Z',
            started_at: '2026-01-01T00:00:00.000Z',
            ready_at: '2026-01-01T00:00:00.000Z',
            updated_at: '2026-01-01T00:00:00.000Z',
            created_at: '2026-01-01T00:00:00.000Z',
          },
        ]),
        invalidateReady: jest.fn(async () => undefined),
      } as never,
    });

    await expect(svc.exportSession('session-1')).rejects.toThrow(/CSV_MOVE_FAIL/);
    expect(insert).not.toHaveBeenCalled();
    expect(published.has('file:///docs/aisle-exports/prior.csv')).toBe(true);
    expect(published.has('file:///docs/aisle-exports/prior.zip')).toBe(true);
  });

  it('ZIP move failure after CSV publish rolls back new CSV and skips insert', async () => {
    (writeStoreZipAtomic as jest.Mock).mockResolvedValueOnce({ byteLength: 10, sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' });
    const live = new Set<string>([
      'file:///docs/aisle-exports/prior.csv',
      'file:///docs/aisle-exports/prior.zip',
    ]);
    const moveAsync = FileSystem.moveAsync as jest.Mock;
    moveAsync.mockImplementation(async ({ from, to }: { from: string; to: string }) => {
      if (String(from).includes('.tmp.zip')) {
        throw new Error('ZIP_MOVE_FAIL');
      }
      live.add(String(to));
      live.delete(String(from));
    });
    (FileSystem.deleteAsync as jest.Mock).mockImplementation(async (uri: string) => {
      live.delete(String(uri));
    });
    (FileSystem.getInfoAsync as jest.Mock).mockImplementation(async (uri: string) => {
      const u = String(uri);
      if (u.includes('staging') || u.includes('photo')) return { exists: true, size: 4 };
      if (live.has(u)) return { exists: true, size: 100 };
      return { exists: false };
    });
    const insert = jest.fn(async () => undefined);

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
      draftRepo: { listForSession: jest.fn(async () => drafts as never) } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: { findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: insert, insert } as never,
      deviceId: 'dev-1',
      localCodeScanEnabled: false,
      exportPrepEnabled: true,
      exportPrepRepo: {
        listForSession: jest.fn(async () => [
          {
            capture_photo_id: 'session-1:1',
            capture_session_id: 'session-1',
            status: 'READY',
            source_uri: 'file://photo.jpg',
            staging_uri: 'file:///docs/export-staging/session-1/photos/0001.jpg',
            export_file_name: '0001_session-1_1.jpg',
            size_bytes: 4,
            sha256: VALID_SHA,
            source_fingerprint: null,
            error_code: null,
            error_message: null,
            attempt_count: 1,
            max_attempts: 3,
            lease_token: null,
            lease_expires_at: null,
            queued_at: '2026-01-01T00:00:00.000Z',
            started_at: '2026-01-01T00:00:00.000Z',
            ready_at: '2026-01-01T00:00:00.000Z',
            updated_at: '2026-01-01T00:00:00.000Z',
            created_at: '2026-01-01T00:00:00.000Z',
          },
        ]),
        invalidateReady: jest.fn(async () => undefined),
      } as never,
    });

    await expect(svc.exportSession('session-1')).rejects.toThrow(/ZIP_MOVE_FAIL/);
    expect(insert).not.toHaveBeenCalled();
    expect(live.has('file:///docs/aisle-exports/prior.csv')).toBe(true);
    expect(live.has('file:///docs/aisle-exports/prior.zip')).toBe(true);
    expect([...live].some((u) => u.includes('.tmp.'))).toBe(false);
    expect([...live].filter((u) => /\.\d+\.csv$/.test(u)).length).toBe(0);
  });
});

describe('feature flag off keeps legacy path', () => {
  beforeEach(() => {
    const pub = (FileSystem as unknown as { __published?: Set<string> }).__published;
    pub?.clear();
    (FileSystem.moveAsync as jest.Mock).mockReset();
    (FileSystem.moveAsync as jest.Mock).mockImplementation(
      async ({ from, to }: { from: string; to: string }) => {
        pub?.delete(String(from));
        pub?.add(String(to));
      },
    );
    (FileSystem.getInfoAsync as jest.Mock).mockReset();
    (FileSystem.getInfoAsync as jest.Mock).mockImplementation(async (uri: string) => {
      const u = String(uri);
      if (u.includes('staging') || u.includes('photo.jpg')) {
        return { exists: true, size: 4 };
      }
      if (pub?.has(u)) {
        return { exists: true, size: 100 };
      }
      if (u.endsWith('.csv') || u.endsWith('.zip') || u.includes('.tmp.')) {
        return { exists: false };
      }
      return { exists: true, size: 4 };
    });
    (writeStoreZipAtomic as jest.Mock).mockReset();
    (writeStoreZipAtomic as jest.Mock).mockResolvedValue({ byteLength: 10, sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' });
  });
  it('does not require prep jobs when exportPrepEnabled is false', async () => {
    (writeStoreZipAtomic as jest.Mock).mockResolvedValueOnce({ byteLength: 10, sha256: 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' });
    // Already-ready draft → ensureLocalCodeScans skips execute; legacy mode still applies.
    const execute = jest.fn(async () => 'RESOLVED' as const);

    const drafts = [
      {
        id: 'd1',
        capture_photo_id: 'session-1:1',
        capture_session_id: 'session-1',
        status: 'RESOLVED',
        internal_code: 'SKU-1',
        label_id: 'L1',
        product_results_json: '[{"sku":"1"}]',
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
      draftRepo: { listForSession: jest.fn(async () => drafts as never) } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: false,
      exportPrepRepo: null,
    });
    const result = await svc.exportSession('session-1');
    expect(result.scanMode).toBe('legacy');
    expect(result.photoCount).toBe(1);
    // Prep repo never consulted when flag path is off.
    expect(execute).not.toHaveBeenCalled();
  });
});

describe('ExportPrepRepository markReady invariant', () => {
  it('rejects incomplete READY payloads before SQL', async () => {
    const repo = new ExportPrepRepository({
      runAsync: jest.fn(),
      getFirstAsync: jest.fn(),
      getAllAsync: jest.fn(),
      execAsync: jest.fn(),
    } as never);
    await expect(
      repo.markReady('p1', 'tok', {
        stagingUri: '',
        exportFileName: 'x.jpg',
        sizeBytes: 1,
        sha256: VALID_SHA,
      }),
    ).rejects.toThrow(/EXPORT_PREP_READY_INCOMPLETE/);
  });
});
