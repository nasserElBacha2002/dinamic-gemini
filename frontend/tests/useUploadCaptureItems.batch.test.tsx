import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { UploadCaptureSessionItemsResponse } from '../src/types/captureSession';

vi.mock('../src/features/uploads/useUploadLimits', () => ({
  useUploadLimits: () => ({
    maxFilesPerRequest: 10,
    maxFileSizeBytes: 500 * 1024 * 1024,
    maxBytesPerRequest: 1024 * 1024 * 1024,
    uploadConcurrency: 2,
    retryAttempts: 1,
    retryBaseDelayMs: 10,
    source: 'fallback' as const,
  }),
}));

vi.mock('../src/features/ingestionSessions/api/captureSessionsApi', () => ({
  CAPTURE_STAGING_MAX_FILES_PER_REQUEST: 10,
  uploadCaptureSessionStagingBatch: vi.fn(),
  stagingResponseToOutcomes: vi.fn((body: UploadCaptureSessionItemsResponse, ids: string[]) => ({
    outcomes: ids.map((id, i) => {
      const err = body.errors.find((e) => e.file_index === i);
      if (err) {
        return { clientFileId: id, status: 'failed' as const, code: err.code, message: err.detail };
      }
      const item = body.items[i] ?? body.items[0];
      return {
        clientFileId: id,
        status: item?.import_status === 'imported' ? ('completed' as const) : ('failed' as const),
        serverId: item?.id,
      };
    }),
  })),
}));

import { uploadCaptureSessionStagingBatch } from '../src/features/ingestionSessions/api/captureSessionsApi';
import { useUploadCaptureItems } from '../src/features/ingestionSessions/hooks/useUploadCaptureItems';

const mockedUpload = vi.mocked(uploadCaptureSessionStagingBatch);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function importedBody(files: File[]): UploadCaptureSessionItemsResponse {
  return {
    items: files.map((f, i) => ({
      id: `item-${i}`,
      session_id: 'sess-1',
      staging_storage_key: `k-${i}`,
      import_status: 'imported' as const,
      assignment_status: 'pending' as const,
      updated_at: '2026-01-01T00:00:00Z',
      original_filename: f.name,
    })),
    errors: [],
  };
}

describe('useUploadCaptureItems — bulk staging flow', () => {
  beforeEach(() => {
    mockedUpload.mockReset();
  });

  it('accepts more than per-request max by batching', async () => {
    mockedUpload.mockImplementation(async ({ files }) => importedBody(files));

    const { result } = renderHook(() => useUploadCaptureItems(), { wrapper: createWrapper() });
    const files = Array.from({ length: 12 }, (_, i) => new File(['x'], `f${i}.jpg`, { type: 'image/jpeg' }));

    let out: Awaited<ReturnType<typeof result.current.upload>>;
    await act(async () => {
      out = await result.current.upload({
        inventoryId: 'inv-1',
        sessionId: 'sess-1',
        files,
      });
    });

    expect(out!.uploadedCount).toBe(12);
    expect(mockedUpload.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('retryFailed after rerender sends only failed file and reuses uploadBatchId', async () => {
    let call = 0;
    mockedUpload.mockImplementation(async ({ files, clientFileIds }) => {
      call += 1;
      if (call === 1) {
        return {
          items: [
            {
              id: 'ok-0',
              session_id: 'sess-1',
              staging_storage_key: 'k0',
              import_status: 'imported' as const,
              assignment_status: 'pending' as const,
              updated_at: '2026-01-01T00:00:00Z',
              original_filename: files[0]?.name,
            },
            {
              id: 'ok-1',
              session_id: 'sess-1',
              staging_storage_key: 'k1',
              import_status: 'imported' as const,
              assignment_status: 'pending' as const,
              updated_at: '2026-01-01T00:00:00Z',
              original_filename: files[1]?.name,
            },
          ],
          errors: [
            {
              file_index: 2,
              code: 'STORAGE_ERROR',
              detail: 'fail',
              filename: files[2]?.name ?? 'c.jpg',
              client_file_id: clientFileIds?.[2] ?? null,
            },
          ],
        };
      }
      return {
        items: files.map((f, i) => ({
          id: `retry-${i}`,
          session_id: 'sess-1',
          staging_storage_key: `kr-${i}`,
          import_status: 'imported' as const,
          assignment_status: 'pending' as const,
          updated_at: '2026-01-01T00:00:00Z',
          original_filename: f.name,
        })),
        errors: [],
      };
    });

    const { result, rerender } = renderHook(() => useUploadCaptureItems(), {
      wrapper: createWrapper(),
    });
    const files = [
      new File(['a'], 'a.jpg', { type: 'image/jpeg' }),
      new File(['b'], 'b.jpg', { type: 'image/jpeg' }),
      new File(['c'], 'c.jpg', { type: 'image/jpeg' }),
    ];

    let firstBatchId = '';
    await act(async () => {
      const first = await result.current.upload({
        inventoryId: 'inv-1',
        sessionId: 'sess-1',
        files,
      });
      firstBatchId = first.uploadBatchId;
      expect(first.uploadedCount).toBe(2);
      expect(first.failedCount).toBe(1);
    });

    rerender();
    await waitFor(() => expect(result.current.lastResult).not.toBeNull());

    mockedUpload.mockClear();
    await act(async () => {
      const retry = await result.current.retryFailed({
        inventoryId: 'inv-1',
        sessionId: 'sess-1',
      });
      expect(retry.uploadBatchId).toBe(firstBatchId);
      expect(retry.uploadedCount).toBe(3);
      expect(retry.failedCount).toBe(0);
    });

    expect(mockedUpload).toHaveBeenCalledTimes(1);
    const retryCall = mockedUpload.mock.calls[0][0];
    expect(retryCall.files).toHaveLength(1);
    expect(retryCall.files[0].name).toBe('c.jpg');
    expect(retryCall.uploadBatchId).toBe(firstBatchId);
  });
});
