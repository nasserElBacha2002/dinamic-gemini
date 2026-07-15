import { describe, expect, it, vi } from 'vitest';
import { executeBulkUpload } from '../src/features/uploads/executeBulkUpload';
import type { BulkBatchUploader } from '../src/features/uploads/bulkUpload.types';

function makeFile(name: string, sizeBytes: number): File {
  const buf = new Uint8Array(Math.min(sizeBytes, 32));
  const f = new File([buf], name, { type: 'image/jpeg' });
  Object.defineProperty(f, 'size', { value: sizeBytes });
  return f;
}

describe('executeBulkUpload', () => {
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
      maxFileSizeBytes: 25e6,
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
      files: [makeFile('big.jpg', 50e6)],
      uploadBatch,
      maxFileSizeBytes: 25e6,
      maxFilesPerBatch: 10,
      maxBytesPerBatch: 100e6,
    });
    expect(uploadBatch).not.toHaveBeenCalled();
    expect(result.failedCount).toBe(1);
    expect(result.files[0].errorCode).toBe('FILE_TOO_LARGE');
  });

  it('supports cancel via AbortSignal', async () => {
    const controller = new AbortController();
    const uploadBatch: BulkBatchUploader = async () => {
      controller.abort();
      await new Promise((r) => setTimeout(r, 50));
      return { outcomes: [] };
    };
    const files = Array.from({ length: 20 }, (_, i) => makeFile(`f${i}.jpg`, 100));
    const result = await executeBulkUpload({
      files,
      uploadBatch,
      signal: controller.signal,
      concurrency: 1,
      maxFilesPerBatch: 5,
      maxBytesPerBatch: 100e6,
      retryAttempts: 1,
    });
    expect(result.cancelledCount + result.completedCount + result.failedCount).toBe(20);
  });
});
