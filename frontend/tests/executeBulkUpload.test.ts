import { describe, expect, it, vi } from 'vitest';
import { executeBulkUpload } from '../src/features/uploads/executeBulkUpload';
import type { BulkBatchUploader } from '../src/features/uploads/bulkUpload.types';
import { ApiError } from '../src/api/types';

function makeFile(name: string, sizeBytes: number): File {
  const buf = new Uint8Array(Math.min(sizeBytes, 32));
  const f = new File([buf], name, { type: 'image/jpeg' });
  Object.defineProperty(f, 'size', { value: sizeBytes });
  return f;
}

describe('executeBulkUpload — cancel, backoff, concurrent progress', () => {
  it('uploads multiple batches with concurrency limit', async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const calls: number[] = [];
    const uploadBatch: BulkBatchUploader = async ({ files }) => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      calls.push(files.length);
      await new Promise((r) => setTimeout(r, 20));
      inFlight -= 1;
      return {
        outcomes: files.map((f) => ({
          clientFileId: f.clientId,
          status: 'completed' as const,
          serverId: `s-${f.clientId}`,
        })),
      };
    };

    const files = Array.from({ length: 25 }, (_, i) => makeFile(`f${i}.jpg`, 1000));
    const result = await executeBulkUpload({
      files,
      uploadBatch,
      concurrency: 2,
      maxFilesPerBatch: 10,
      maxBytesPerBatch: 100e6,
      maxFileSizeBytes: 500e6,
      retryAttempts: 1,
    });

    expect(result.completedCount).toBe(25);
    expect(result.failedCount).toBe(0);
    expect(maxInFlight).toBeLessThanOrEqual(2);
    expect(calls.reduce((a, b) => a + b, 0)).toBe(25);
  });

  it('marks client-side oversized without calling uploader', async () => {
    const uploadBatch = vi.fn();
    const result = await executeBulkUpload({
      files: [makeFile('big.jpg', 600e6)],
      uploadBatch,
      maxFileSizeBytes: 500e6,
      maxFilesPerBatch: 10,
      maxBytesPerBatch: 1024e6,
    });
    expect(uploadBatch).not.toHaveBeenCalled();
    expect(result.failedCount).toBe(1);
    expect(result.files[0].errorCode).toBe('FILE_TOO_LARGE');
  });

  it('cancels during active XHR and resolves with phase cancelled', async () => {
    const controller = new AbortController();
    const uploadBatch: BulkBatchUploader = async ({ signal }) => {
      controller.abort();
      await new Promise((r) => setTimeout(r, 30));
      if (signal.aborted) {
        const err = new Error('Aborted');
        err.name = 'AbortError';
        throw err;
      }
      return { outcomes: [] };
    };
    const files = Array.from({ length: 10 }, (_, i) => makeFile(`f${i}.jpg`, 100));
    const snaps: string[] = [];
    const result = await executeBulkUpload({
      files,
      uploadBatch,
      signal: controller.signal,
      concurrency: 2,
      maxFilesPerBatch: 5,
      maxBytesPerBatch: 100e6,
      retryAttempts: 1,
      onProgress: (s) => snaps.push(s.phase),
    });
    expect(result.cancelledCount).toBeGreaterThan(0);
    expect(snaps).toContain('cancelled');
    expect(result.cancelledCount + result.completedCount + result.failedCount).toBe(10);
  });

  it('cancels during backoff between retries without throwing', async () => {
    const controller = new AbortController();
    let attempts = 0;
    const uploadBatch: BulkBatchUploader = async () => {
      attempts += 1;
      if (attempts === 1) {
        controller.abort();
        throw new ApiError('temp', 503, { code: 'NETWORK_ERROR' });
      }
      throw new Error('should not retry after abort');
    };
    const result = await executeBulkUpload({
      files: [makeFile('a.jpg', 100)],
      uploadBatch,
      signal: controller.signal,
      concurrency: 1,
      maxFilesPerBatch: 1,
      maxBytesPerBatch: 100e6,
      retryAttempts: 3,
      retryBaseDelayMs: 50,
    });
    expect(attempts).toBe(1);
    expect(result.cancelledCount).toBe(1);
    expect(result.failedCount).toBe(0);
  });

  it('keeps concurrent progress monotonic and within 0..100', async () => {
    const progressPcts: number[] = [];
    const holders: { a: (() => void) | null; b: (() => void) | null } = { a: null, b: null };
    let batchN = 0;

    const uploadBatch: BulkBatchUploader = async ({ files, onByteProgress }) => {
      const idx = batchN++;
      const total = files.reduce((s, f) => s + f.file.size, 0);
      if (idx === 0) {
        onByteProgress(Math.round(total * 0.7), total);
        await new Promise<void>((r) => {
          holders.a = r;
        });
        onByteProgress(Math.round(total * 0.9), total);
        holders.a = null;
      } else {
        onByteProgress(Math.round(total * 0.2), total);
        await new Promise<void>((r) => {
          holders.b = r;
        });
        onByteProgress(Math.round(total * 0.5), total);
        holders.a?.();
        await new Promise((r) => setTimeout(r, 5));
        holders.b = null;
      }
      return {
        outcomes: files.map((f) => ({
          clientFileId: f.clientId,
          status: 'completed' as const,
          serverId: f.clientId,
        })),
      };
    };

    const files = [makeFile('a.jpg', 1000), makeFile('b.jpg', 1000)];
    const run = executeBulkUpload({
      files,
      uploadBatch,
      concurrency: 2,
      maxFilesPerBatch: 1,
      maxBytesPerBatch: 100e6,
      maxFileSizeBytes: 500e6,
      retryAttempts: 1,
      onProgress: (s) => {
        progressPcts.push(s.progressPct);
        expect(s.progressPct).toBeGreaterThanOrEqual(0);
        expect(s.progressPct).toBeLessThanOrEqual(100);
      },
    });

    await new Promise((r) => setTimeout(r, 20));
    holders.b?.();
    await new Promise((r) => setTimeout(r, 20));
    holders.a?.();
    const result = await run;

    expect(result.completedCount).toBe(2);
    expect(progressPcts.at(-1)).toBe(100);
    for (let i = 1; i < progressPcts.length; i++) {
      expect(progressPcts[i]).toBeGreaterThanOrEqual(progressPcts[i - 1]);
    }
  });

  it('includes failed file bytes in progress completion', async () => {
    const progressPcts: number[] = [];
    const uploadBatch: BulkBatchUploader = async ({ files }) => ({
      outcomes: files.map((f, i) =>
        i === 0
          ? { clientFileId: f.clientId, status: 'completed' as const, serverId: 'ok' }
          : {
              clientFileId: f.clientId,
              status: 'failed' as const,
              code: 'STORAGE_ERROR',
              message: 'fail',
            }
      ),
    });
    const result = await executeBulkUpload({
      files: [makeFile('a.jpg', 500), makeFile('b.jpg', 500)],
      uploadBatch,
      concurrency: 1,
      maxFilesPerBatch: 2,
      maxBytesPerBatch: 100e6,
      retryAttempts: 1,
      onProgress: (s) => progressPcts.push(s.progressPct),
    });
    expect(result.failedCount).toBe(1);
    expect(result.completedCount).toBe(1);
    expect(progressPcts.at(-1)).toBe(100);
  });
});
