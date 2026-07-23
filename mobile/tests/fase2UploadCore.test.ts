import { buildAllMicroBatches, buildMicroBatch } from '../src/core/uploadBatching';
import { computeRetryDelayMs } from '../src/core/uploadBackoff';
import { classifyUploadHttpError, isSoftPerFileRetryable } from '../src/core/uploadErrors';
import {
  packingBudgetFromServer,
  relaxPackingBudgetAfterSuccess,
  shrinkPackingBudgetAfter413,
} from '../src/core/uploadPackingBudget';
import {
  canTransitionSession,
  isCaptureExclusiveSession,
  mapRemoteJobStatus,
} from '../src/core/captureState';
import { MIGRATIONS } from '../src/database/migrations/migrations';

describe('uploadBatching', () => {
  const limits = {
    maxFilesPerRequest: 3,
    maxFileSizeBytes: 1000,
    maxRequestSizeBytes: 2000,
  };

  it('respects file count and byte limits', () => {
    const batch = buildMicroBatch(
      [
        { photoId: 'a', clientFileId: 'ca', sizeBytes: 800, dateAdded: 1, assetId: '1' },
        { photoId: 'b', clientFileId: 'cb', sizeBytes: 800, dateAdded: 2, assetId: '2' },
        { photoId: 'c', clientFileId: 'cc', sizeBytes: 800, dateAdded: 3, assetId: '3' },
      ],
      limits,
    );
    expect(batch?.photoIds).toEqual(['a', 'b']);
    expect(batch?.totalBytes).toBe(1600);
  });

  it('packs many prepared photos into successive micro-batches (20+ capture)', () => {
    const candidates = Array.from({ length: 24 }, (_, i) => ({
      photoId: `p${i}`,
      clientFileId: `c${i}`,
      sizeBytes: 400,
      dateAdded: i,
      assetId: String(i).padStart(3, '0'),
    }));
    const batches = buildAllMicroBatches(candidates, {
      maxFilesPerRequest: 5,
      maxFileSizeBytes: 1000,
      maxRequestSizeBytes: 2000,
      requirePositiveSize: true,
    });
    // 5 files * 400 = 2000 → exactly 5 per batch → 24/5 = 5 batches (last has 4)
    expect(batches).toHaveLength(5);
    expect(batches.reduce((n, b) => n + b.photoIds.length, 0)).toBe(24);
    expect(batches[0]?.totalBytes).toBe(2000);
    expect(batches[4]?.photoIds).toHaveLength(4);
  });

  it('prepare-first mode skips unknown and oversize sizes', () => {
    const batch = buildMicroBatch(
      [
        { photoId: 'unknown', clientFileId: 'u', sizeBytes: 0, dateAdded: 1, assetId: '1' },
        { photoId: 'big', clientFileId: 'b', sizeBytes: 5000, dateAdded: 2, assetId: '2' },
        { photoId: 'ok', clientFileId: 'd', sizeBytes: 100, dateAdded: 3, assetId: '3' },
      ],
      { ...limits, requirePositiveSize: true },
    );
    expect(batch?.photoIds).toEqual(['ok']);
  });

  it('legacy mode still includes unknown sizes for older paths', () => {
    const batch = buildMicroBatch(
      [
        { photoId: 'unknown', clientFileId: 'u', sizeBytes: 0, dateAdded: 1, assetId: '1' },
        { photoId: 'ok', clientFileId: 'd', sizeBytes: 100, dateAdded: 2, assetId: '2' },
      ],
      limits,
    );
    expect(batch?.photoIds).toEqual(['unknown', 'ok']);
  });

  it('builds multiple batches', () => {
    const batches = buildAllMicroBatches(
      [
        { photoId: 'a', clientFileId: '1', sizeBytes: 900, dateAdded: 1, assetId: 'a' },
        { photoId: 'b', clientFileId: '2', sizeBytes: 900, dateAdded: 2, assetId: 'b' },
        { photoId: 'c', clientFileId: '3', sizeBytes: 900, dateAdded: 3, assetId: 'c' },
      ],
      { maxFilesPerRequest: 2, maxFileSizeBytes: 1000, maxRequestSizeBytes: 2500 },
    );
    expect(batches).toHaveLength(2);
    expect(batches[0]?.photoIds).toEqual(['a', 'b']);
    expect(batches[1]?.photoIds).toEqual(['c']);
  });
});

describe('uploadPackingBudget', () => {
  const server = {
    maxFilesPerRequest: 10,
    maxRequestSizeBytes: 80_000_000,
    maxFileSizeBytes: 25_000_000,
  };

  it('starts from server limits', () => {
    expect(packingBudgetFromServer(server)).toEqual({
      maxFiles: 10,
      maxRequestBytes: 80_000_000,
      maxFileBytes: 25_000_000,
    });
  });

  it('shrinks after 413 so the failed payload is not repeated', () => {
    const current = packingBudgetFromServer(server);
    const next = shrinkPackingBudgetAfter413({
      current,
      server,
      failedBatchFileCount: 5,
      failedBatchBytes: 40_000_000,
    });
    expect(next.maxFiles).toBeLessThanOrEqual(2);
    expect(next.maxRequestBytes).toBeLessThan(40_000_000);
    expect(next.maxFileBytes).toBeLessThanOrEqual(next.maxRequestBytes);
  });

  it('relaxes toward server limits after success', () => {
    const shrunk = shrinkPackingBudgetAfter413({
      current: packingBudgetFromServer(server),
      server,
      failedBatchFileCount: 5,
      failedBatchBytes: 40_000_000,
    });
    const relaxed = relaxPackingBudgetAfterSuccess({ current: shrunk, server });
    expect(relaxed.maxFiles).toBeGreaterThanOrEqual(shrunk.maxFiles);
    expect(relaxed.maxRequestBytes).toBeGreaterThanOrEqual(shrunk.maxRequestBytes);
    expect(relaxed.maxFiles).toBeLessThanOrEqual(server.maxFilesPerRequest);
  });
});

describe('uploadBackoff', () => {
  it('grows exponentially with capped jitter', () => {
    const d0 = computeRetryDelayMs({ attempt: 0, baseDelayMs: 1000, random: () => 0 });
    const d2 = computeRetryDelayMs({ attempt: 2, baseDelayMs: 1000, random: () => 0 });
    expect(d0).toBe(1000);
    expect(d2).toBe(4000);
  });
});

describe('uploadErrors', () => {
  it('classifies http statuses', () => {
    expect(classifyUploadHttpError(401, null)).toBe('auth');
    expect(classifyUploadHttpError(503, null)).toBe('retryable');
    expect(classifyUploadHttpError(409, 'ACTIVE_JOB_EXISTS')).toBe('conflict_blocked');
    expect(classifyUploadHttpError(422, 'CLIENT_FILE_IDS_MISMATCH')).toBe('validation');
    expect(classifyUploadHttpError(413, 'UPLOAD_REQUEST_TOO_LARGE')).toBe('payload_too_large');
    expect(classifyUploadHttpError(413, null)).toBe('payload_too_large');
  });

  it('classifies soft per-file codes', () => {
    expect(isSoftPerFileRetryable('UNSUPPORTED_ASSET_TYPE')).toBe(false);
    expect(isSoftPerFileRetryable('ASSET_PERSIST_FAILED')).toBe(true);
    expect(isSoftPerFileRetryable('UPLOAD_FILE_TOO_LARGE')).toBe(false);
  });
});

describe('fase2 session transitions', () => {
  it('allows review -> uploading and processing terminal paths', () => {
    expect(canTransitionSession('review', 'uploading')).toBe(true);
    expect(canTransitionSession('uploading', 'ready_to_process')).toBe(true);
    expect(canTransitionSession('ready_to_process', 'processing')).toBe(true);
    expect(canTransitionSession('processing', 'completed')).toBe(true);
    expect(canTransitionSession('processing', 'failed_processing')).toBe(true);
  });

  it('marks exclusive capture statuses', () => {
    expect(isCaptureExclusiveSession('active')).toBe(true);
    expect(isCaptureExclusiveSession('uploading')).toBe(false);
    expect(isCaptureExclusiveSession('processing')).toBe(false);
  });

  it('maps remote job statuses', () => {
    expect(mapRemoteJobStatus('queued')).toBe('pending');
    expect(mapRemoteJobStatus('running')).toBe('running');
    expect(mapRemoteJobStatus('succeeded')).toBe('success');
    expect(mapRemoteJobStatus('canceled')).toBe('cancelled');
  });
});

describe('fase2 migrations', () => {
  it('includes v3 and v4 upload/job schema', () => {
    expect(MIGRATIONS.map((m) => m.version)).toEqual([1, 2, 3, 4, 5]);
    const sql = MIGRATIONS.map((m) => m.sql).join('\n');
    expect(sql).toContain('upload_batch_id');
    expect(sql).toContain('client_file_id');
    expect(sql).toContain('observability_events');
    expect(sql).toContain('CREATE TABLE IF NOT EXISTS upload_batches');
    expect(sql).toContain('CREATE TABLE IF NOT EXISTS processing_jobs');
    expect(sql).toContain('idx_capture_photos_session_client_file');
  });
});
