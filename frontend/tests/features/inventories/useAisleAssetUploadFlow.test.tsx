import type { MutableRefObject, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAisleAssetUploadFlow } from '../../../src/features/inventories/hooks/useAisleAssetUploadFlow';
import type { BulkUploadRunResult } from '../../../src/features/uploads';

const executeBulkUploadMock = vi.fn();
const showSnackbarMock = vi.fn();
const addEventListenerMock = vi.spyOn(window, 'addEventListener');

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) =>
      opts?.count != null ? `${key}:${opts.count}` : key,
  }),
}));

vi.mock('../../../src/components/ui/useAppSnackbar', () => ({
  useAppSnackbar: () => ({
    showSnackbar: showSnackbarMock,
    closeSnackbar: vi.fn(),
  }),
}));

vi.mock('../../../src/features/uploads/executeBulkUpload', () => ({
  executeBulkUpload: (...args: unknown[]) => executeBulkUploadMock(...args),
}));

vi.mock('../../../src/features/uploads/useUploadLimits', () => ({
  useUploadLimits: () => ({
    maxFilesPerRequest: 10,
    maxFileSizeBytes: 500 * 1024 * 1024,
    maxBytesPerRequest: 1024 * 1024 * 1024,
    uploadConcurrency: 2,
    retryAttempts: 3,
    retryBaseDelayMs: 1000,
    source: 'fallback' as const,
  }),
}));

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQueryClient: () => ({
      invalidateQueries: vi.fn(),
    }),
  };
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function okResult(count: number): BulkUploadRunResult {
  return {
    uploadBatchId: 'batch-1',
    files: [],
    completedCount: count,
    failedCount: 0,
    cancelledCount: 0,
    uploadedBytes: count,
    totalBytes: count,
  };
}

describe('useAisleAssetUploadFlow', () => {
  beforeEach(() => {
    executeBulkUploadMock.mockReset();
    showSnackbarMock.mockReset();
    addEventListenerMock.mockClear();
  });

  it('exposes isUploadingPhotos while upload runs and registers beforeunload', async () => {
    executeBulkUploadMock.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() => useAisleAssetUploadFlow({ inventoryId: 'inv-1' }), {
      wrapper,
    });

    act(() => {
      void result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      ]);
    });

    await waitFor(() => {
      expect(result.current.isUploadingPhotos).toBe(true);
    });

    const beforeUnloadAdds = addEventListenerMock.mock.calls.filter(([event]) => event === 'beforeunload');
    expect(beforeUnloadAdds.length).toBeGreaterThan(0);
  });

  it('does not start a second upload while one is in progress', async () => {
    let resolveFirst: (value: BulkUploadRunResult) => void = () => {};
    executeBulkUploadMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        })
    );

    const { result } = renderHook(() => useAisleAssetUploadFlow({ inventoryId: 'inv-1' }), {
      wrapper,
    });

    act(() => {
      void result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a1.jpg', { type: 'image/jpeg' }),
      ]);
    });

    await waitFor(() => {
      expect(result.current.isUploadingPhotos).toBe(true);
    });

    await act(async () => {
      await result.current.handleFilesSelectedForAisle('aisle-2', [
        new File(['y'], 'b.jpg', { type: 'image/jpeg' }),
      ]);
    });

    expect(executeBulkUploadMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst(okResult(1));
    });

    await waitFor(() => {
      expect(result.current.isUploadingPhotos).toBe(false);
    });
  });

  it('does not open file picker while an upload is in progress', async () => {
    executeBulkUploadMock.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() => useAisleAssetUploadFlow({ inventoryId: 'inv-1' }), {
      wrapper,
    });

    const clickSpy = vi.fn();
    const input = document.createElement('input');
    input.type = 'file';
    input.click = clickSpy;
    act(() => {
      (result.current.fileInputRef as MutableRefObject<HTMLInputElement | null>).current = input;
    });

    act(() => {
      void result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      ]);
    });

    await waitFor(() => {
      expect(result.current.isUploadingPhotos).toBe(true);
    });

    act(() => {
      result.current.beginUploadForAisle('aisle-2');
    });

    expect(clickSpy).not.toHaveBeenCalled();
  });

  it('shows count-based success snackbar when result includes assets', async () => {
    executeBulkUploadMock.mockResolvedValue(okResult(2));

    const { result } = renderHook(() => useAisleAssetUploadFlow({ inventoryId: 'inv-1' }), {
      wrapper,
    });

    await act(async () => {
      await result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      ]);
    });

    expect(result.current.isUploadingPhotos).toBe(false);
    expect(showSnackbarMock).toHaveBeenCalledWith('aisle.assets_uploaded_snackbar:2', 'success');
  });

  it('shows normalized error snackbar on failure and clears uploading state', async () => {
    executeBulkUploadMock.mockRejectedValue(new Error('network'));

    const { result } = renderHook(() => useAisleAssetUploadFlow({ inventoryId: 'inv-1' }), {
      wrapper,
    });

    await act(async () => {
      await result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      ]);
    });

    expect(result.current.isUploadingPhotos).toBe(false);
    expect(showSnackbarMock).toHaveBeenCalledWith(expect.any(String), 'error');
    expect(result.current.uploadError).toBeTruthy();
  });
});
