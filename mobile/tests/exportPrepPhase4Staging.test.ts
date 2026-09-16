/**
 * Phase 4: export ZIP from validated staging — resolver, policy, skip-scan, blockers.
 */

import { LocalCsvExportService } from '../src/features/localCsv/localCsvExportService';
import { decideExportSourcePolicy } from '../src/features/exportPrep/exportSourcePolicy';
import {
  resolveExportPhotosFromStaging,
  resolveExportPhotosFromOriginals,
} from '../src/features/exportPrep/exportPhotoResolver';
import { ExportFromStagingError } from '../src/features/exportPrep/exportFromStagingErrors';
import {
  assertModernZipPhotosArePrepEligible,
  selectExpectedZipPhotos,
} from '../src/features/exportPrep/eligibleExportPhotos';
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
      if (u.includes('missing-staging')) {
        return { exists: false };
      }
      if (u.includes('staging') || u.includes('photo') || u.includes('original')) {
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

const SHA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const now = '2026-01-01T00:00:00.000Z';

function session(overrides: Partial<CaptureSessionRow> = {}): CaptureSessionRow {
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
    capture_freeze_generation: 2,
    active_freeze_id: 'freeze-1',
    upload_policy: 'MANUAL',
    created_at: now,
    updated_at: now,
    ...overrides,
  } as CaptureSessionRow;
}

function photo(overrides: Partial<CapturePhotoRow> = {}): CapturePhotoRow {
  return {
    id: 'session-1:1',
    capture_session_id: 'session-1',
    asset_id: '1',
    media_store_numeric_id: 1,
    uri: 'file://original/photo.jpg',
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
    ...overrides,
  } as CapturePhotoRow;
}

function readyJob(overrides: Record<string, unknown> = {}) {
  return {
    capture_photo_id: 'session-1:1',
    capture_session_id: 'session-1',
    status: 'READY',
    source_uri: 'file://original/photo.jpg',
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
    ...overrides,
  };
}

function resolvedDraft() {
  return {
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
  };
}

describe('Phase 4 export source policy', () => {
  it('flag off → legacy originals with FEATURE_DISABLED', () => {
    const d = decideExportSourcePolicy({ exportPrepEnabled: false });
    expect(d.mode).toBe('legacy_originals');
    expect(d.fallbackReason).toBe('FEATURE_DISABLED');
  });

  it('flag on → staging required (no silent fallback)', () => {
    const d = decideExportSourcePolicy({ exportPrepEnabled: true });
    expect(d.mode).toBe('staging_required');
    expect(d.fallbackReason).toBeNull();
  });
});

describe('Phase 4 expected ZIP set', () => {
  it('excludes excluded/rejected from expected ZIP photos', () => {
    const photos = [
      photo({ id: 'a', status: 'stable' }),
      photo({ id: 'b', status: 'excluded' }),
      photo({ id: 'c', status: 'rejected' }),
    ];
    expect(selectExpectedZipPhotos(photos).map((p) => p.id)).toEqual(['a']);
  });

  it('rejects non-stable photos on modern prep path', () => {
    expect(() =>
      assertModernZipPhotosArePrepEligible([
        photo({ id: 'a', status: 'stable' }),
        photo({ id: 'b', status: 'waiting_stability' }),
      ]),
    ).toThrow(/PHOTO_SET_MISMATCH|PACKAGE_EXPORT_PHOTO_SET_MISMATCH/);
  });
});

describe('Phase 4 resolveExportPhotosFromStaging', () => {
  it('1. all READY → VALIDATED_STAGING and does not use original URI as bytes source', async () => {
    const invalidateReady = jest.fn();
    const result = await resolveExportPhotosFromStaging({
      session: session(),
      expectedPhotos: [photo()],
      jobsByPhotoId: new Map([['session-1:1', readyJob() as never]]),
      prepRepo: { invalidateReady } as never,
    });
    expect(result.photos).toHaveLength(1);
    expect(result.photos[0]!.source).toBe('VALIDATED_STAGING');
    expect(result.photos[0]!.uri).toContain('staging');
    expect(result.photos[0]!.uri).not.toContain('original');
    expect(result.stagingCount).toBe(1);
    expect(result.originalFallbackCount).toBe(0);
    expect(result.allStagingStrongValidated).toBe(true);
    expect(invalidateReady).not.toHaveBeenCalled();
  });

  it('2. missing staging → invalidates READY and does not fall back', async () => {
    const invalidateReady = jest.fn(async () => undefined);
    await expect(
      resolveExportPhotosFromStaging({
        session: session(),
        expectedPhotos: [photo()],
        jobsByPhotoId: new Map([
          [
            'session-1:1',
            readyJob({
              staging_uri: 'file:///docs/missing-staging.jpg',
            }) as never,
          ],
        ]),
        prepRepo: { invalidateReady } as never,
      }),
    ).rejects.toBeInstanceOf(ExportFromStagingError);
    expect(invalidateReady).toHaveBeenCalled();
  });

  it('5. missing job on modern session → PREP_JOB_MISSING (no fallback)', async () => {
    await expect(
      resolveExportPhotosFromStaging({
        session: session(),
        expectedPhotos: [photo()],
        jobsByPhotoId: new Map(),
        prepRepo: { invalidateReady: jest.fn() } as never,
      }),
    ).rejects.toMatchObject({ code: 'PREP_JOB_MISSING' });
  });

  it('9. unsafe / non-deterministic export_file_name → fails before ZIP', async () => {
    const p1 = photo({ id: 'session-1:1', sequence_number: 1 });
    const p2 = photo({ id: 'session-1:2', sequence_number: 2, display_name: 'photo.jpg' });
    await expect(
      resolveExportPhotosFromStaging({
        session: session(),
        expectedPhotos: [p1, p2],
        jobsByPhotoId: new Map([
          ['session-1:1', readyJob({ export_file_name: 'dup.jpg' }) as never],
          [
            'session-1:2',
            readyJob({
              capture_photo_id: 'session-1:2',
              export_file_name: 'dup.jpg',
            }) as never,
          ],
        ]),
        prepRepo: { invalidateReady: jest.fn() } as never,
      }),
    ).rejects.toMatchObject({ code: 'PACKAGE_VALIDATION_FAILED' });
  });
});

describe('Phase 4 controlled original fallback', () => {
  it('6/7. legacy originals path marks CONTROLLED_ORIGINAL_FALLBACK', async () => {
    const result = await resolveExportPhotosFromOriginals({
      session: session({ active_freeze_id: null }),
      expectedPhotos: [photo()],
      fallbackReason: 'FEATURE_DISABLED',
    });
    expect(result.photos[0]!.source).toBe('CONTROLLED_ORIGINAL_FALLBACK');
    expect(result.fallbackReason).toBe('FEATURE_DISABLED');
    expect(result.originalFallbackCount).toBe(1);
    expect(result.stagingCount).toBe(0);
  });
});

describe('Phase 4 LocalCsvExportService integration', () => {
  function makeSvc(opts: {
    execute?: jest.Mock;
    jobs?: unknown[];
    photos?: CapturePhotoRow[];
    sessionRow?: CaptureSessionRow;
    exportPrepEnabled?: boolean;
    getSessionImpl?: () => Promise<CaptureSessionRow | null>;
  }) {
    const execute = opts.execute ?? jest.fn(async () => 'RESOLVED' as const);
    let sessionCalls = 0;
    const getSession =
      opts.getSessionImpl ??
      (async () => {
        sessionCalls += 1;
        return opts.sessionRow ?? session();
      });
    const invalidateReady = jest.fn(async () => undefined);
    const svc = new LocalCsvExportService({
      captureRepo: {
        getSession,
        listPhotos: jest.fn(async () => opts.photos ?? [photo()]),
        listFreezePhotos: jest.fn(async () => opts.photos ?? [photo()]),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => [resolvedDraft()] as never),
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
      localCodeScan: { execute } as never,
      localCodeScanEnabled: true,
      exportPrepEnabled: opts.exportPrepEnabled !== false,
      exportPrepRepo:
        opts.exportPrepEnabled === false
          ? null
          : ({
              listForSession: jest.fn(async () => opts.jobs ?? [readyJob()]),
              invalidateReady,
            } as never),
    });
    return { svc, execute, invalidateReady, getSessionCalls: () => sessionCalls };
  }

  it('1. all READY → staging counts + skip CODE_SCAN', async () => {
    const { svc, execute } = makeSvc({});
    const result = await svc.exportSession('session-1');
    expect(execute).not.toHaveBeenCalled();
    expect(result.scanMode).toBe('skipped_all_ready');
    expect(result.stagingPhotoCount).toBe(1);
    expect(result.originalFallbackCount).toBe(0);
    expect(result.photoCount).toBe(1);
  });

  it('7. feature flag off → legacy path + original fallback counts', async () => {
    const { svc, execute } = makeSvc({ exportPrepEnabled: false });
    const result = await svc.exportSession('session-1');
    // Draft already export-ready → catch-up scan may no-op, but packaging is originals.
    expect(result.scanMode).toBe('legacy');
    expect(result.originalFallbackCount).toBe(1);
    expect(result.fallbackReason).toBe('FEATURE_DISABLED');
    expect(result.stagingPhotoCount).toBe(0);
    expect(execute).not.toHaveBeenCalled();
  });

  it('8. excluded photo is omitted and does not block', async () => {
    const photos = [
      photo({ id: 'session-1:1', status: 'stable', sequence_number: 1 }),
      photo({ id: 'session-1:2', status: 'excluded', sequence_number: 2 }),
    ];
    const { svc, execute } = makeSvc({
      photos,
      jobs: [readyJob({ capture_photo_id: 'session-1:1' })],
    });
    const result = await svc.exportSession('session-1');
    expect(execute).not.toHaveBeenCalled();
    expect(result.photoCount).toBe(1);
    expect(result.stagingPhotoCount).toBe(1);
  });

  it('10. freeze changed during export → blocks publish', async () => {
    let n = 0;
    const { svc } = makeSvc({
      getSessionImpl: async () => {
        n += 1;
        if (n === 1) {
          return session({ active_freeze_id: 'freeze-1', capture_freeze_generation: 2 });
        }
        return session({ active_freeze_id: 'freeze-2', capture_freeze_generation: 3 });
      },
    });
    await expect(svc.exportSession('session-1')).rejects.toMatchObject({
      code: 'FREEZE_CHANGED',
    });
  });

  it('11. concurrent exports for same session serialize (no throw)', async () => {
    const { svc } = makeSvc({});
    const [a, b] = await Promise.all([
      svc.exportSession('session-1'),
      svc.exportSession('session-1'),
    ]);
    expect(a.photoCount).toBe(1);
    expect(b.photoCount).toBe(1);
    expect(a.scanMode).toBe('skipped_all_ready');
    expect(b.scanMode).toBe('skipped_all_ready');
  });

  it('blocks when job still QUEUED', async () => {
    const { svc } = makeSvc({
      jobs: [readyJob({ status: 'QUEUED', staging_uri: null, sha256: null, size_bytes: null })],
    });
    await expect(svc.exportSession('session-1')).rejects.toThrow(/PACKAGE_EXPORT_PREP_PENDING/);
  });

  it('scales to 10 and 100 READY photos without CODE_SCAN', async () => {
    for (const n of [10, 100]) {
      const photos = Array.from({ length: n }, (_, i) =>
        photo({
          id: `session-1:${i + 1}`,
          sequence_number: i + 1,
          asset_id: String(i + 1),
          client_file_id: `cf-${i + 1}`,
        }),
      );
      const jobs = photos.map((p, i) =>
        readyJob({
          capture_photo_id: p.id,
          export_file_name: `${String(i + 1).padStart(4, '0')}_${p.id.replace(/:/g, '_')}.jpg`,
          staging_uri: `file:///docs/export-staging/session-1/photos/${p.id}.jpg`,
        }),
      );
      const drafts = photos.map((p) => ({
        ...resolvedDraft(),
        id: `d-${p.id}`,
        capture_photo_id: p.id,
      }));
      const execute = jest.fn(async () => 'RESOLVED' as const);
      const svc = new LocalCsvExportService({
        captureRepo: {
          getSession: jest.fn(async () => session()),
          listPhotos: jest.fn(async () => photos),
          listFreezePhotos: jest.fn(async () => photos),
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
        exportPrepEnabled: true,
        exportPrepRepo: {
          listForSession: jest.fn(async () => jobs),
          invalidateReady: jest.fn(async () => undefined),
        } as never,
      });
      const started = Date.now();
      const result = await svc.exportSession('session-1');
      const elapsed = Date.now() - started;
      expect(execute).not.toHaveBeenCalled();
      expect(result.scanMode).toBe('skipped_all_ready');
      expect(result.stagingPhotoCount).toBe(n);
      expect(result.originalFallbackCount).toBe(0);
      expect(result.photoCount).toBe(n);
      // Soft budget: mocked FS should stay well under a few seconds even at 100.
      expect(elapsed).toBeLessThan(15_000);
    }
  });
});
