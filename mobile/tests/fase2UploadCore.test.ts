import { buildAllMicroBatches, buildMicroBatch } from '../src/core/uploadBatching';
import { computeRetryDelayMs } from '../src/core/uploadBackoff';
import { classifyUploadHttpError, isSoftPerFileRetryable } from '../src/core/uploadErrors';
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

  it('skips oversized individual files', () => {
    const batch = buildMicroBatch(
      [
        { photoId: 'big', clientFileId: 'c', sizeBytes: 5000, dateAdded: 1, assetId: '9' },
        { photoId: 'ok', clientFileId: 'd', sizeBytes: 100, dateAdded: 2, assetId: '1' },
      ],
      limits,
    );
    expect(batch?.photoIds).toEqual(['ok']);
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
  });

  it('classifies soft per-file codes', () => {
    expect(isSoftPerFileRetryable('UNSUPPORTED_ASSET_TYPE')).toBe(false);
    expect(isSoftPerFileRetryable('ASSET_PERSIST_FAILED')).toBe(true);
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
    expect(MIGRATIONS.map((m) => m.version)).toEqual([1, 2, 3, 4]);
    const sql = MIGRATIONS.map((m) => m.sql).join('\n');
    expect(sql).toContain('upload_batch_id');
    expect(sql).toContain('client_file_id');
    expect(sql).toContain('CREATE TABLE IF NOT EXISTS upload_batches');
    expect(sql).toContain('CREATE TABLE IF NOT EXISTS processing_jobs');
    expect(sql).toContain('idx_capture_photos_session_client_file');
  });
});
