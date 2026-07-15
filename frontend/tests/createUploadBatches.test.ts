import { describe, expect, it } from 'vitest';
import { createUploadBatches, partitionUploadFiles } from '../src/features/uploads/createUploadBatches';
import type { BulkUploadFileResult } from '../src/features/uploads/bulkUpload.types';

function makeFile(name: string, sizeBytes: number): File {
  const buf = new Uint8Array(Math.min(sizeBytes, 64));
  const f = new File([buf], name, { type: 'image/jpeg' });
  Object.defineProperty(f, 'size', { value: sizeBytes });
  return f;
}

function rowsFromFiles(files: File[]): BulkUploadFileResult[] {
  return files.map((file, i) => ({
    clientId: `c${i}`,
    file,
    status: 'pending' as const,
    progress: 0,
    attempts: 0,
  }));
}

describe('createUploadBatches', () => {
  it('handles 0 files', () => {
    expect(createUploadBatches([], { maxFilesPerBatch: 5, maxBytesPerBatch: 30e6 })).toEqual([]);
  });

  it('handles 1 file', () => {
    const batches = createUploadBatches(rowsFromFiles([makeFile('a.jpg', 1e6)]), {
      maxFilesPerBatch: 5,
      maxBytesPerBatch: 30e6,
    });
    expect(batches).toHaveLength(1);
    expect(batches[0].files).toHaveLength(1);
  });

  it('splits by file count', () => {
    const files = Array.from({ length: 12 }, (_, i) => makeFile(`f${i}.jpg`, 100));
    const batches = createUploadBatches(rowsFromFiles(files), {
      maxFilesPerBatch: 5,
      maxBytesPerBatch: 100e6,
    });
    expect(batches.map((b) => b.files.length)).toEqual([5, 5, 2]);
  });

  it('splits by bytes (12 x 8MB, maxFiles=5, maxBytes=30MB → batches of 3)', () => {
    const files = Array.from({ length: 12 }, (_, i) => makeFile(`f${i}.jpg`, 8e6));
    const batches = createUploadBatches(rowsFromFiles(files), {
      maxFilesPerBatch: 5,
      maxBytesPerBatch: 30e6,
    });
    expect(batches.map((b) => b.files.length)).toEqual([3, 3, 3, 3]);
  });

  it('preserves order', () => {
    const files = [makeFile('a.jpg', 1), makeFile('b.jpg', 1), makeFile('c.jpg', 1)];
    const batches = createUploadBatches(rowsFromFiles(files), {
      maxFilesPerBatch: 2,
      maxBytesPerBatch: 100e6,
    });
    expect(batches[0].files.map((f) => f.file.name)).toEqual(['a.jpg', 'b.jpg']);
    expect(batches[1].files.map((f) => f.file.name)).toEqual(['c.jpg']);
  });
});

describe('partitionUploadFiles', () => {
  it('marks oversized files failed and keeps valid', () => {
    const { valid, oversized } = partitionUploadFiles(
      [makeFile('ok.jpg', 1000), makeFile('big.jpg', 50e6)],
      { maxFilesPerBatch: 10, maxBytesPerBatch: 100e6, maxFileSizeBytes: 25e6 }
    );
    expect(valid).toHaveLength(1);
    expect(oversized).toHaveLength(1);
    expect(oversized[0].errorCode).toBe('FILE_TOO_LARGE');
  });
});
