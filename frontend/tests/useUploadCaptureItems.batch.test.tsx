import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { UploadCaptureSessionItemsResponse } from '../src/types/captureSession';

vi.mock('../src/features/ingestionSessions/api/captureSessionsApi', () => ({
  CAPTURE_STAGING_MAX_FILES_PER_REQUEST: 50,
  uploadCaptureSessionStagingFiles: vi.fn(),
}));

import { uploadCaptureSessionStagingFiles } from '../src/features/ingestionSessions/api/captureSessionsApi';
import { useUploadCaptureItems } from '../src/features/ingestionSessions/hooks/useUploadCaptureItems';

const mockedUpload = vi.mocked(uploadCaptureSessionStagingFiles);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useUploadCaptureItems — batch staging flow', () => {
  beforeEach(() => {
    mockedUpload.mockReset();
  });

  it('mixed 201 items+errors: correct uploadedCount, failedCount, and per-row queue state', async () => {
    const response: UploadCaptureSessionItemsResponse = {
      items: [
        {
          id: 'item-ok',
          session_id: 'sess-1',
          staging_storage_key: 'capture/staging/ok',
          import_status: 'imported',
          assignment_status: 'pending',
          updated_at: '2026-01-01T00:00:00Z',
          original_filename: 'ok.jpg',
        },
      ],
      errors: [
        {
          filename: 'bad.jpg',
          code: 'ZERO_BYTE_FILE',
          detail: 'Empty or zero-byte files are not allowed',
          file_index: 1,
        },
      ],
    };
    mockedUpload.mockResolvedValue(response);

    const { result } = renderHook(() => useUploadCaptureItems(), { wrapper: createWrapper() });

    const okFile = new File(['x'], 'ok.jpg', { type: 'image/jpeg' });
    const emptyFile = new File([], 'bad.jpg', { type: 'image/jpeg' });

    const lastQueues: Array<{ state: string; error?: string }[]> = [];

    let out: Awaited<ReturnType<typeof result.current.mutateAsync>>;
    await act(async () => {
      out = await result.current.mutateAsync({
        inventoryId: 'inv-1',
        sessionId: 'sess-1',
        files: [okFile, emptyFile],
        onQueueUpdate: (q) => {
          lastQueues.push(q.map((row) => ({ state: row.state, error: row.error })));
        },
      });
    });

    expect(mockedUpload).toHaveBeenCalledTimes(1);
    expect(mockedUpload).toHaveBeenCalledWith('inv-1', 'sess-1', [okFile, emptyFile], undefined, expect.any(Function));

    expect(out!.uploadedCount).toBe(1);
    expect(out!.failedCount).toBe(1);
    expect(out!.queue).toHaveLength(2);
    expect(out!.queue[0].state).toBe('uploaded');
    expect(out!.queue[1].state).toBe('failed');
    expect(out!.queue[1].error).toContain('ZERO_BYTE_FILE');

    const terminal = lastQueues[lastQueues.length - 1];
    expect(terminal[0].state).toBe('uploaded');
    expect(terminal[1].state).toBe('failed');
  });
});
