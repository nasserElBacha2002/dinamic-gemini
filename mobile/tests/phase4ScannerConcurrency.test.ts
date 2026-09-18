/**
 * Phase 4 — ExportPrepQueue maxWorkers 1|2 and LocalCodeScanStrategy setMaxConcurrency.
 *
 * Note: Phase 4 A/B benches keep exportPrepMaxWorkers=2 (constant feed) and only
 * vary scannerConcurrency. workers=1 would starve scanner C=2 (scans run only in processJob).
 * These unit tests still exercise setMaxWorkers(2) in isolation (queue capability).
 */

import { ExportPrepFenceError } from '../src/database/repositories/exportPrepRepository';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { LocalCodeScanStrategy } from '../src/features/localCodeScan/localCodeScanStrategy';
import type { ExportPrepJobRow } from '../src/features/exportPrep/exportPrepTypes';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 12 })),
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
  classifyStagedDigestError: jest.fn(() => ({
    failure: 'STAGING_DIGEST_FAILED',
    code: 'EXPORT_PREP_HASH_FAILED',
    reason: 'digest_io_failed',
  })),
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

function queuedJob(photoId: string, lease: string): ExportPrepJobRow {
  return {
    capture_photo_id: photoId,
    capture_session_id: 's1',
    status: 'PREPARING',
    source_uri: 'file://photo.jpg',
    staging_uri: null,
    export_file_name: null,
    size_bytes: null,
    sha256: null,
    source_fingerprint: 'fp',
    error_code: null,
    error_message: null,
    attempt_count: 0,
    max_attempts: 3,
    lease_token: lease,
    lease_expires_at: '2099-01-01T00:00:00.000Z',
    queued_at: '2026-01-01T00:00:00.000Z',
    started_at: '2026-01-01T00:00:00.000Z',
    ready_at: null,
    updated_at: '2026-01-01T00:00:00.000Z',
    created_at: '2026-01-01T00:00:00.000Z',
  };
}

function photo(id: string, seq: number) {
  return {
    id,
    capture_session_id: 's1',
    uri: 'file://photo.jpg',
    status: 'stable',
    size: 12,
    width: 1,
    height: 1,
    sequence_number: seq,
    display_name: `${id}.jpg`,
  };
}

function emptyCounts() {
  return {
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
  };
}

describe('phase4 scanner / prep concurrency', () => {
  test('setMaxWorkers rejects values other than 1|2', () => {
    const queue = new ExportPrepQueue({
      prepRepo: {
        claimNext: jest.fn(async () => null),
        countsForSession: jest.fn(async () => emptyCounts()),
        recoverInterrupted: jest.fn(async () => 0),
      } as never,
      captureRepo: {} as never,
      draftRepo: {} as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      maxWorkers: 1,
    });
    expect(() => queue.setMaxWorkers(0)).toThrow(/EXPORT_PREP_MAX_WORKERS_INVALID/);
    expect(() => queue.setMaxWorkers(3)).toThrow(/EXPORT_PREP_MAX_WORKERS_INVALID/);
    expect(() => queue.setMaxWorkers(1)).not.toThrow();
    expect(() => queue.setMaxWorkers(2)).not.toThrow();
    expect(queue.getMaxWorkers()).toBe(2);
    queue.stop();
  });

  test('two workers spawn; maxObservedWorkers <= 2', async () => {
    const jobs = [queuedJob('p1', 'lease-1'), queuedJob('p2', 'lease-2')];
    let claimIdx = 0;
    const claimNext = jest.fn(async () => {
      if (claimIdx >= jobs.length) return null;
      const j = jobs[claimIdx]!;
      claimIdx += 1;
      return j;
    });

    const gate = { release: null as (() => void) | null };
    const hold = new Promise<void>((resolve) => {
      gate.release = resolve;
    });

    const getPhotoById = jest.fn(async (id: string) => {
      await hold;
      return photo(id, id === 'p1' ? 1 : 2);
    });

    const markReady = jest.fn(async () => undefined);
    const markScanning = jest.fn(async () => undefined);
    const markValidating = jest.fn(async () => undefined);
    const renewLease = jest.fn(async () => undefined);
    const markFailedFenced = jest.fn(async () => undefined);

    const queue = new ExportPrepQueue({
      prepRepo: {
        claimNext,
        countsForSession: jest.fn(async () => emptyCounts()),
        recoverInterrupted: jest.fn(async () => 0),
        renewLease,
        markScanning,
        markValidating,
        markReady,
        markFailedFenced,
        releaseLeasesForSession: jest.fn(async () => undefined),
      } as never,
      captureRepo: {
        getPhotoById,
      } as never,
      draftRepo: {
        getBySessionAndPhotoId: jest.fn(async () => ({
          draft: {
            status: 'RESOLVED',
            product_results_json: '[]',
            error_code: null,
          },
        })),
      } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      maxWorkers: 2,
    });

    queue.setMaxWorkers(2);
    queue.wake();

    await new Promise((r) => setTimeout(r, 20));
    expect(queue.getActiveWorkers()).toBe(2);
    expect(queue.getMaxObservedWorkers()).toBeLessThanOrEqual(2);
    expect(queue.getMaxObservedWorkers()).toBe(2);

    gate.release?.();
    await new Promise((r) => setTimeout(r, 50));
    queue.stop();
    expect(queue.getMaxObservedWorkers()).toBeLessThanOrEqual(2);
  });

  test('failure in one processJob does not clear the other worker path', async () => {
    const jobs = [queuedJob('fail', 'lease-fail'), queuedJob('ok', 'lease-ok')];
    let claimIdx = 0;
    const claimNext = jest.fn(async () => {
      if (claimIdx >= jobs.length) return null;
      const j = jobs[claimIdx]!;
      claimIdx += 1;
      return j;
    });

    const markReady = jest.fn(async () => undefined);
    const markFailedFenced = jest.fn(async () => undefined);

    const queue = new ExportPrepQueue({
      prepRepo: {
        claimNext,
        countsForSession: jest.fn(async () => emptyCounts()),
        recoverInterrupted: jest.fn(async () => 0),
        renewLease: jest.fn(async () => undefined),
        markScanning: jest.fn(async () => undefined),
        markValidating: jest.fn(async () => undefined),
        markReady,
        markFailedFenced,
        releaseLeasesForSession: jest.fn(async () => undefined),
      } as never,
      captureRepo: {
        getPhotoById: jest.fn(async (id: string) => {
          if (id === 'fail') {
            throw Object.assign(new Error('boom'), { code: 'EXPORT_PREP_FAILED' });
          }
          return photo(id, 2);
        }),
      } as never,
      draftRepo: {
        getBySessionAndPhotoId: jest.fn(async () => ({
          draft: {
            status: 'RESOLVED',
            product_results_json: '[]',
            error_code: null,
          },
        })),
      } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      maxWorkers: 2,
    });

    queue.setMaxWorkers(2);
    queue.wake();
    await new Promise((r) => setTimeout(r, 80));
    queue.stop();

    expect(markFailedFenced).toHaveBeenCalled();
    expect(markReady).toHaveBeenCalled();
    expect(queue.metrics.jobsFailed).toBeGreaterThanOrEqual(1);
    expect(queue.metrics.jobsCompleted).toBeGreaterThanOrEqual(1);
    // Ensure fence error type remains distinct (sanity for isolation).
    expect(ExportPrepFenceError).toBeDefined();
  });

  test('LOCAL strategy setMaxConcurrency accepts only 1|2', () => {
    const strategy = new LocalCodeScanStrategy({
      drafts: {
        upsertDraft: jest.fn(),
        recoverStaleScanning: jest.fn(async () => 0),
        listForSession: jest.fn(async () => []),
      } as never,
    });
    expect(() => strategy.setMaxConcurrency(0)).toThrow(/LOCAL_SCAN_MAX_CONCURRENCY_INVALID/);
    expect(() => strategy.setMaxConcurrency(3)).toThrow(/LOCAL_SCAN_MAX_CONCURRENCY_INVALID/);
    strategy.setMaxConcurrency(1);
    expect(strategy.getMaxConcurrency()).toBe(1);
    strategy.setMaxConcurrency(2);
    expect(strategy.getMaxConcurrency()).toBe(2);
    expect(() => strategy.resetConcurrencyStats()).not.toThrow();
    expect(strategy.getMaxObservedConcurrency()).toBe(0);
  });
});
