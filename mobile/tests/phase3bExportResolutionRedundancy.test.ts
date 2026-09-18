/**
 * Phase 3B — eliminate redundant EXPORT_PREFLIGHT strong rehash;
 * reuse canonical photos + jobs snapshot from ensure.
 */

import {
  emptyEnsureExportPrepJobsResult,
  type EnsureExportPrepJobsResult,
} from '../src/features/exportPrep/exportPrepTypes';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { validateReadyStaging } from '../src/features/exportPrep/validateReadyStaging';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async (uri: string) => {
    if (String(uri).includes('missing')) return { exists: false };
    return { exists: true, size: 12 };
  }),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(async () => 'c'.repeat(64)),
  hashStagedFileSha256Detailed: jest.fn(async () => ({
    sha256: 'c'.repeat(64),
    bytesHashed: 12,
    hashMode: 'native_file' as const,
    hashSource: 'computed' as const,
    durationMs: 1,
  })),
  classifyStagedDigestError: jest.fn(() => ({ failure: 'STAGING_DIGEST_FAILED' })),
}));

jest.mock('../src/features/exportPrep/digestAbsoluteFile', () => ({
  assertNativeDigestCapability: jest.fn(),
}));

jest.mock('../src/features/exportPrep/exportStaging', () => ({
  stageOriginalPhotoVersioned: jest.fn(async () => ({
    stagingUri: 'file:///docs/export-staging/s1/0001_p1.jpg',
    sizeBytes: 12,
  })),
  deleteSessionExportStaging: jest.fn(async () => undefined),
  stagingFileExists: jest.fn(async () => true),
}));

const SHA = 'c'.repeat(64);

function readyJob(photoId: string) {
  return {
    capture_photo_id: photoId,
    capture_session_id: 's1',
    status: 'READY' as const,
    source_uri: 'file://photo.jpg',
    staging_uri: 'file:///docs/export-staging/s1/0001_p1.jpg',
    export_file_name: '0001_p1.jpg',
    size_bytes: 12,
    sha256: SHA,
    source_fingerprint: 'fp',
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
  };
}

describe('phase3b export_resolution redundancy reduction', () => {
  test('EnsureExportPrepJobsResult defaults include phase3b fields', () => {
    const empty = emptyEnsureExportPrepJobsResult('s1', 'EXPORT_PREFLIGHT');
    expect(empty.readyValidationMode).toBe('light');
    expect(empty.readyValidatedCount).toBe(0);
    expect(empty.reusedCanonicalPhotos).toBe(false);
    expect(empty.batchedJobLookup).toBe(false);
    expect(empty.jobsSnapshot).toBeUndefined();
  });

  test('EXPORT_PREFLIGHT uses light READY check (no strong digests)', async () => {
    const { hashStagedFileSha256Hex } = jest.requireMock(
      '../src/features/exportPrep/stagedSha256',
    ) as { hashStagedFileSha256Hex: jest.Mock };
    hashStagedFileSha256Hex.mockClear();

    const photo = {
      id: 'p1',
      capture_session_id: 's1',
      uri: 'file://photo.jpg',
      status: 'stable',
      size: 12,
      width: 1,
      height: 1,
      sequence_number: 1,
      display_name: 'p1.jpg',
    };

    const session = {
      id: 's1',
      active_freeze_id: null,
      capture_freeze_generation: null,
    };

    const jobs = [readyJob('p1')];
    const getByPhotoId = jest.fn(async () => {
      throw new Error('N+1 getByPhotoId must not be used');
    });
    const listForSession = jest.fn(async () => jobs);
    const invalidateReady = jest.fn(async () => undefined);
    const countsForSession = jest.fn(async () => ({
      queued: 0,
      preparing: 0,
      scanning: 0,
      validating: 0,
      ready: 1,
      failedRetryable: 0,
      failedTerminal: 0,
      excluded: 0,
      pending: 0,
      processing: 0,
      failed: 0,
      total: 1,
    }));

    const queue = new ExportPrepQueue({
      prepRepo: {
        listForSession,
        getByPhotoId,
        invalidateReady,
        countsForSession,
        enqueueIdempotent: jest.fn(),
        markExcluded: jest.fn(),
        claimNext: jest.fn(async () => null),
        recoverInterrupted: jest.fn(async () => 0),
      } as never,
      captureRepo: {
        getSession: jest.fn(async () => session),
        listPhotos: jest.fn(async () => [photo]),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: {} as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      maxWorkers: 1,
    });

    const result: EnsureExportPrepJobsResult = await queue.ensureJobsForEligiblePhotos('s1', {
      reason: 'EXPORT_PREFLIGHT',
      session: session as never,
      photos: [photo as never],
    });

    // Prevent background tick after ensure scheduleTick.
    queue.stop();

    expect(result.readyValidationMode).toBe('light');
    expect(result.readyValidatedCount).toBe(1);
    expect(result.reusedCanonicalPhotos).toBe(true);
    expect(result.batchedJobLookup).toBe(true);
    expect(result.jobsSnapshot?.length).toBe(1);
    expect(result.jobsSnapshotToken).toMatch(/^jsnap_/);
    expect(result.jobsSnapshotSessionId).toBe('s1');
    expect(result.activeWorkersAtSnapshot).toBe(0);
    expect(result.invalidatedReadyJobs).toBe(0);
    expect(hashStagedFileSha256Hex).not.toHaveBeenCalled();
    expect(getByPhotoId).not.toHaveBeenCalled();
    expect(listForSession).toHaveBeenCalledTimes(1);
  });

  test('light completeness still invalidates size mismatch', async () => {
    const bad = { ...readyJob('p1'), size_bytes: 999 };
    const invalidateReady = jest.fn(async () => undefined);
    const enqueueIdempotent = jest.fn(async () => ({ created: false, requeued: true }));

    const queue = new ExportPrepQueue({
      prepRepo: {
        listForSession: jest.fn(async () => [bad]),
        getByPhotoId: jest.fn(),
        invalidateReady,
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
        enqueueIdempotent,
        markExcluded: jest.fn(),
        claimNext: jest.fn(async () => null),
        recoverInterrupted: jest.fn(async () => 0),
      } as never,
      captureRepo: {
        getSession: jest.fn(async () => ({ id: 's1' })),
        listPhotos: jest.fn(async () => []),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: {} as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      maxWorkers: 1,
    });

    const photo = {
      id: 'p1',
      capture_session_id: 's1',
      uri: 'file://photo.jpg',
      status: 'stable',
      size: 12,
      width: 1,
      height: 1,
      sequence_number: 1,
      display_name: 'p1.jpg',
    };

    const result = await queue.ensureJobsForEligiblePhotos('s1', {
      reason: 'EXPORT_PREFLIGHT',
      session: { id: 's1' } as never,
      photos: [photo as never],
    });
    queue.stop();

    expect(result.invalidatedReadyJobs).toBe(1);
    expect(invalidateReady).toHaveBeenCalled();
    expect(result.jobsSnapshot).toBeUndefined();
  });

  test('strong validation at packaging still native-rehashes (integrity intact)', async () => {
    const { hashStagedFileSha256Hex } = jest.requireMock(
      '../src/features/exportPrep/stagedSha256',
    ) as { hashStagedFileSha256Hex: jest.Mock };
    hashStagedFileSha256Hex.mockClear();
    const result = await validateReadyStaging(readyJob('p1'), 'strong');
    expect(result.ok).toBe(true);
    expect(hashStagedFileSha256Hex).toHaveBeenCalledTimes(1);
    expect(result.digest?.hashSource).toBe('computed');
  });

  test('concurrency knobs default to 1 and accept 2 via setMaxWorkers', () => {
    const queue = new ExportPrepQueue({
      prepRepo: {
        claimNext: jest.fn(async () => null),
        listForSession: jest.fn(async () => []),
        getByPhotoId: jest.fn(),
        invalidateReady: jest.fn(),
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
        enqueueIdempotent: jest.fn(),
        markExcluded: jest.fn(),
        recoverInterrupted: jest.fn(async () => 0),
      } as never,
      captureRepo: {
        getSession: jest.fn(async () => ({ id: 's1' })),
        listPhotos: jest.fn(async () => []),
        listFreezePhotos: jest.fn(async () => []),
      } as never,
      draftRepo: {} as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      maxWorkers: 1,
    });
    expect(queue.getMaxWorkers()).toBe(1);
    queue.setMaxWorkers(2);
    expect(queue.getMaxWorkers()).toBe(2);
    expect(() => queue.setMaxWorkers(3)).toThrow(/EXPORT_PREP_MAX_WORKERS_INVALID/);
    queue.stop();
  });
});
