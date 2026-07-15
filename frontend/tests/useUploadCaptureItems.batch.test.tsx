import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { UploadCaptureSessionItemsResponse } from '../src/types/captureSession';

vi.mock('../src/features/ingestionSessions/api/captureSessionsApi', () => ({
  CAPTURE_STAGING_MAX_FILES_PER_REQUEST: 10,
  uploadCaptureSessionStagingBatch: vi.fn(),
  stagingResponseToOutcomes: vi.fn((body: UploadCaptureSessionItemsResponse, ids: string[]) => ({
    outcomes: ids.map((id, i) => {
      const err = body.errors.find((e) => e.file_index === i);
      if (err) {
        return { clientFileId: id, status: 'failed' as const, code: err.code, message: err.detail };
      }
      const item = body.items.find((_, idx) => idx === i) ?? body.items[0];
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

describe('useUploadCaptureItems — bulk staging flow', () => {
  beforeEach(() => {
    mockedUpload.mockReset();
  });

  it('accepts more than per-request max by batching', async () => {
    mockedUpload.mockImplementation(async ({ files }) => ({
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
    }));

    const { result } = renderHook(() => useUploadCaptureItems(), { wrapper: createWrapper() });
    const files = Array.from({ length: 12 }, (_, i) => new File(['x'], `f${i}.jpg`, { type: 'image/jpeg' }));

    let out: Awaited<ReturnType<typeof result.current.mutateAsync>>;
    await act(async () => {
      out = await result.current.mutateAsync({
        inventoryId: 'inv-1',
        sessionId: 'sess-1',
        files,
      });
    });

    expect(out!.uploadedCount).toBe(12);
    expect(mockedUpload.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
