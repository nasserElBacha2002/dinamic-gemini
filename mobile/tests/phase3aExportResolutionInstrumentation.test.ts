/**
 * Phase 3A — export_resolution substages instrumentation (no functional optimization).
 */

import { LocalCsvExportService } from '../src/features/localCsv/localCsvExportService';
import type { LocalExportPhaseEvent } from '../src/features/localCsv/localCsvExportService';
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

jest.mock('../src/features/exportPrep/validateReadyStaging', () => ({
  validateReadyStaging: jest.fn(async () => ({
    ok: true,
    digest: {
      sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      bytesHashed: 4,
      hashMode: 'native_file',
      hashSource: 'computed',
      durationMs: 2,
      reason: null,
    },
  })),
  isConfirmedReadyIntegrityFailure: jest.fn(() => false),
}));

describe('phase3a export_resolution substages', () => {
  const now = '2026-01-01T00:00:00.000Z';
  const SHA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

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

  function buildService() {
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
    return new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => [photo()]),
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
      localCodeScan: { execute: jest.fn(async () => 'RESOLVED') } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      ensureExportPrepJobs: jest.fn(async () => undefined),
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
            sha256: SHA,
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
  }

  test('emits aggregate export_resolution and measurable substages', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    const svc = buildService();
    const result = await svc.exportSession('session-1', {
      onExportPhase: (e) => phases.push(e),
    });

    expect(result.photoCount).toBe(1);
    const names = phases.map((p) => p.phase);
    expect(names).toContain('export_resolution');
    expect(names).toContain('export_resolution_queries');
    expect(names).toContain('export_resolution_ensure_jobs');
    expect(names).toContain('export_resolution_staging_validation');
    expect(names).toContain('export_resolution_hash_validation');
    expect(names).toContain('export_resolution_profile');
    expect(names).toContain('export_resolution_entry_build');
    expect(names).toContain('strong_validation');
    expect(names).toContain('strong_validation_hash');

    const aggregate = phases.find((p) => p.phase === 'export_resolution')!;
    expect(aggregate.success).toBe(true);
    expect(aggregate.extras?.nestedHashInStaging).toBe(true);
    expect(aggregate.extras?.reconciliation).toEqual(expect.any(String));

    const hashEvents = phases.filter((p) => p.phase === 'strong_validation_hash');
    expect(hashEvents.length).toBe(1);
    expect(hashEvents[0]!.photoId).toBe('session-1:1');
    expect(hashEvents[0]!.sequence).toBe(1);
    expect(hashEvents[0]!.extras?.digestReused).toBe(false);
    expect(hashEvents[0]!.extras?.base64FullFileHashCount).toBe(0);
  });

  test('observer errors do not change export result', async () => {
    const svc = buildService();
    const result = await svc.exportSession('session-1', {
      onExportPhase: () => {
        throw new Error('observer boom');
      },
    });
    expect(result.photoCount).toBe(1);
    expect(result.scanMode).toBe('skipped_all_ready');
  });

  test('export without observer still succeeds (instrumentation optional)', async () => {
    const svc = buildService();
    const result = await svc.exportSession('session-1');
    expect(result.photoCount).toBe(1);
  });

  test('hash_validation duration is digest sum and can differ from staging wall', async () => {
    const { validateReadyStaging } = jest.requireMock(
      '../src/features/exportPrep/validateReadyStaging',
    ) as { validateReadyStaging: jest.Mock };
    validateReadyStaging.mockImplementationOnce(async () => {
      await new Promise((r) => setTimeout(r, 25));
      return {
        ok: true,
        digest: {
          sha256: SHA,
          bytesHashed: 4,
          hashMode: 'native_file',
          hashSource: 'computed',
          durationMs: 3,
          reason: null,
        },
      };
    });

    const phases: LocalExportPhaseEvent[] = [];
    await buildService().exportSession('session-1', { onExportPhase: (e) => phases.push(e) });

    const staging = phases.find((p) => p.phase === 'export_resolution_staging_validation')!;
    const hash = phases.find((p) => p.phase === 'export_resolution_hash_validation')!;
    expect(hash.durationMs).toBe(3);
    expect(staging.durationMs).toBeGreaterThanOrEqual(hash.durationMs);
    expect(staging.durationMs).not.toBe(hash.durationMs);
    expect(hash.extras?.hashCount).toBe(1);
    expect(hash.extras?.bytesHashed).toBe(4);
    expect(hash.extras?.fullFileReadCount).toBe(1);
    expect(hash.extras?.photoCount).toBe(1);
    expect(hash.extras?.nestParent).toBe('export_resolution_staging_validation');
  });

  test('ensure_jobs and profile never report fictitious queryCount -1', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    await buildService().exportSession('session-1', { onExportPhase: (e) => phases.push(e) });
    const ensure = phases.find((p) => p.phase === 'export_resolution_ensure_jobs')!;
    const profile = phases.find((p) => p.phase === 'export_resolution_profile')!;
    expect(ensure.extras?.queryCount).toBeNull();
    expect(ensure.extras?.queryCountKnown).toBe(false);
    expect(profile.extras?.queryCount).toBeNull();
    expect(profile.extras?.queryCountKnown).toBe(false);
    expect(profile.extras?.profileResolverPresent).toBe(false);
  });

  test('aggregate reconciliation fields are present and additive excludes nested hash', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    await buildService().exportSession('session-1', { onExportPhase: (e) => phases.push(e) });
    const agg = phases.find((p) => p.phase === 'export_resolution')!;
    const additive =
      Number(agg.extras?.queriesDurationMs) +
      Number(agg.extras?.ensureJobsDurationMs) +
      Number(agg.extras?.stagingValidationDurationMs) +
      Number(agg.extras?.scanCatchupDurationMs) +
      Number(agg.extras?.profileDurationMs) +
      Number(agg.extras?.entryBuildDurationMs) +
      Number(agg.extras?.otherDurationMs);
    expect(agg.extras?.additiveSubstageMs).toBe(additive);
    expect(typeof agg.extras?.unaccountedMs).toBe('number');
    expect(typeof agg.extras?.reconciliationValid).toBe('boolean');
    // Nested hash must not be double-counted into additive.
    expect(Number(agg.extras?.additiveSubstageMs)).toBeLessThanOrEqual(
      Number(agg.extras?.queriesDurationMs) +
        Number(agg.extras?.ensureJobsDurationMs) +
        Number(agg.extras?.stagingValidationDurationMs) +
        Number(agg.extras?.scanCatchupDurationMs) +
        Number(agg.extras?.profileDurationMs) +
        Number(agg.extras?.entryBuildDurationMs) +
        Number(agg.extras?.otherDurationMs) +
        0.0001,
    );
    expect(agg.extras?.hashValidationDurationMs).toBeDefined();
  });

  test('draftRepo list failure emits queries success=false with fallbackUsed', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    const failing = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => [photo()]),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => {
          throw new Error('draft boom');
        }),
      } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
        markShared: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute: jest.fn(async () => 'RESOLVED') } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      ensureExportPrepJobs: jest.fn(async () => undefined),
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
            sha256: SHA,
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

    // Without resolved draft, export should fail on blockers — still must emit failure-aware queries.
    await expect(
      failing.exportSession('session-1', { onExportPhase: (e) => phases.push(e) }),
    ).rejects.toThrow();
    const queries = phases.find((p) => p.phase === 'export_resolution_queries');
    expect(queries).toBeDefined();
    expect(queries!.success).toBe(false);
    expect(queries!.extras?.fallbackUsed).toBe(true);
    expect(queries!.errorCode).toBe('DRAFT_LIST_FALLBACK_EMPTY');
  });

  test('ensureExportPrepJobs failure emits ensure_jobs success=false', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => [photo()]),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => [
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
        ] as never),
      } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
        markShared: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute: jest.fn(async () => 'RESOLVED') } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      ensureExportPrepJobs: jest.fn(async () => {
        const err = new Error('ensure failed') as Error & { code?: string };
        err.code = 'ENSURE_FAILED';
        throw err;
      }),
      exportPrepRepo: {
        listForSession: jest.fn(async () => []),
        invalidateReady: jest.fn(async () => undefined),
      } as never,
    });

    await expect(
      svc.exportSession('session-1', { onExportPhase: (e) => phases.push(e) }),
    ).rejects.toThrow(/ensure failed/);
    const ensure = phases.find((p) => p.phase === 'export_resolution_ensure_jobs');
    expect(ensure?.success).toBe(false);
    expect(ensure?.errorCode).toBe('ENSURE_FAILED');
    expect(ensure?.extras?.queryCount).toBeNull();
    expect(ensure?.extras?.queryCountKnown).toBe(false);
  });

  test('confirmedRepo failure emits profile success=false with fallbackUsed', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => [photo()]),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => [
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
        ] as never),
      } as never,
      confirmedRepo: {
        listForSession: jest.fn(async () => {
          throw new Error('confirmed boom');
        }),
      } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
        markShared: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute: jest.fn(async () => 'RESOLVED') } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      ensureExportPrepJobs: jest.fn(async () => undefined),
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
            sha256: SHA,
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

    await svc.exportSession('session-1', { onExportPhase: (e) => phases.push(e) });
    const profile = phases.find((p) => p.phase === 'export_resolution_profile')!;
    expect(profile.success).toBe(false);
    expect(profile.errorCode).toBe('CONFIRMED_LIST_FALLBACK_EMPTY');
    expect(profile.extras?.fallbackUsed).toBe(true);
  });

  test('profile resolver failure emits profile success=false', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession: jest.fn(async () => session()),
        listPhotos: jest.fn(async () => [photo()]),
        listFreezePhotos: jest.fn(async () => [photo()]),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => [
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
        ] as never),
      } as never,
      confirmedRepo: { listForSession: jest.fn(async () => []) } as never,
      exportRepo: {
        findByFingerprint: jest.fn(async () => null),
        findBySessionAndFingerprint: jest.fn(async () => null),
        tryInsert: jest.fn(async () => true),
        insert: jest.fn(async () => undefined),
        markShared: jest.fn(async () => undefined),
      } as never,
      deviceId: 'dev-1',
      localCodeScan: { execute: jest.fn(async () => 'RESOLVED') } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: true,
      ensureExportPrepJobs: jest.fn(async () => undefined),
      profileResolver: {
        resolveForAisle: jest.fn(async () => {
          throw new Error('profile boom');
        }),
      } as never,
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
            sha256: SHA,
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

    await svc.exportSession('session-1', { onExportPhase: (e) => phases.push(e) });
    const profile = phases.find((p) => p.phase === 'export_resolution_profile')!;
    expect(profile.success).toBe(false);
    expect(profile.errorCode).toBe('PROFILE_RESOLVE_FALLBACK_NULL');
    expect(profile.extras?.fallbackUsed).toBe(true);
    expect(profile.extras?.profileResolverPresent).toBe(true);
    expect(profile.extras?.profileResolved).toBe(false);
  });

  test('staging digest failure emits staging/hash success=false', async () => {
    const { validateReadyStaging } = jest.requireMock(
      '../src/features/exportPrep/validateReadyStaging',
    ) as { validateReadyStaging: jest.Mock };
    validateReadyStaging.mockImplementationOnce(async () => ({
      ok: false,
      failure: 'STAGING_SHA_MISMATCH',
      digest: {
        sha256: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        bytesHashed: 4,
        hashMode: 'native_file',
        hashSource: 'computed',
        durationMs: 2,
        reason: null,
      },
    }));

    const phases: LocalExportPhaseEvent[] = [];
    await expect(
      buildService().exportSession('session-1', { onExportPhase: (e) => phases.push(e) }),
    ).rejects.toThrow();
    const staging = phases.find((p) => p.phase === 'export_resolution_staging_validation');
    const hash = phases.find((p) => p.phase === 'export_resolution_hash_validation');
    expect(staging?.success).toBe(false);
    expect(hash?.success).toBe(false);
    expect(hash?.extras?.nestParent).toBe('export_resolution_staging_validation');
  });

  test('no Base64 full-file hash counters on resolution stages', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    await buildService().exportSession('session-1', { onExportPhase: (e) => phases.push(e) });
    for (const p of phases.filter((x) => String(x.phase).startsWith('export_resolution'))) {
      expect(p.extras?.base64FullFileHashCount ?? 0).toBe(0);
    }
    const strong = phases.filter((p) => p.phase === 'strong_validation_hash');
    expect(strong.every((p) => p.extras?.base64FullFileHashCount === 0)).toBe(true);
  });

  test('required phase3a stages are emitted exactly once on staging path', async () => {
    const phases: LocalExportPhaseEvent[] = [];
    await buildService().exportSession('session-1', { onExportPhase: (e) => phases.push(e) });
    const required = [
      'export_resolution',
      'export_resolution_queries',
      'export_resolution_ensure_jobs',
      'export_resolution_staging_validation',
      'export_resolution_hash_validation',
      'export_resolution_scan_catchup',
      'export_resolution_profile',
      'export_resolution_freeze_checks',
      'export_resolution_entry_build',
    ];
    for (const name of required) {
      expect(phases.filter((p) => p.phase === name)).toHaveLength(1);
    }
  });
});
