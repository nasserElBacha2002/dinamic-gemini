import { describe, it, expect } from 'vitest';
import { applyStagingChunkResult } from '../src/features/ingestionSessions/hooks/useUploadCaptureItems';
import type { UploadCaptureSessionItemsResponse } from '../src/types/captureSession';

function makeFile(name: string, body: string): File {
  return new File([body], name, { type: 'image/jpeg' });
}

describe('applyStagingChunkResult', () => {
  it('marks rows from structured errors and successful imported items', () => {
    const files = [makeFile('a.jpg', 'x'), makeFile('b.jpg', 'y'), makeFile('c.jpg', 'z')];
    const queue = files.map((file, i) => ({
      key: `k-${i}`,
      file,
      state: 'uploading' as const,
      progressPct: 50,
    }));
    const result: UploadCaptureSessionItemsResponse = {
      items: [
        {
          id: 'i0',
          session_id: 's',
          staging_storage_key: 'k0',
          import_status: 'imported',
          assignment_status: 'pending',
          updated_at: '2026-01-01T00:00:00Z',
          original_filename: 'a.jpg',
        },
        {
          id: 'i2',
          session_id: 's',
          staging_storage_key: 'k2',
          import_status: 'imported',
          assignment_status: 'pending',
          updated_at: '2026-01-01T00:00:00Z',
          original_filename: 'c.jpg',
        },
      ],
      errors: [{ filename: 'b.jpg', code: 'ZERO_BYTE_FILE', detail: 'Empty', file_index: 1 }],
    };
    applyStagingChunkResult(queue, 0, files, result);
    expect(queue[0].state).toBe('uploaded');
    expect(queue[1].state).toBe('failed');
    expect(queue[1].error).toContain('ZERO_BYTE_FILE');
    expect(queue[2].state).toBe('uploaded');
  });

  it('marks failed when server returns import_failed row without validation error', () => {
    const files = [makeFile('a.jpg', 'x')];
    const queue = [{ key: 'k0', file: files[0], state: 'uploading' as const, progressPct: 0 }];
    const result: UploadCaptureSessionItemsResponse = {
      items: [
        {
          id: 'i0',
          session_id: 's',
          staging_storage_key: 'k0',
          import_status: 'import_failed',
          assignment_status: 'pending',
          updated_at: '2026-01-01T00:00:00Z',
          original_filename: 'a.jpg',
          last_error_code: 'STORAGE_WRITE_FAILED',
          last_error_detail: 'Staging storage write failed',
        },
      ],
      errors: [],
    };
    applyStagingChunkResult(queue, 0, files, result);
    expect(queue[0].state).toBe('failed');
    expect(queue[0].error).toContain('STORAGE_WRITE_FAILED');
  });
});
