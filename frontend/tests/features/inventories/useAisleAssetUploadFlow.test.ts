import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useAisleAssetUploadFlow } from '../../../src/features/inventories/hooks/useAisleAssetUploadFlow';

const mutateAsyncMock = vi.fn();
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

vi.mock('../../../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../src/hooks')>();
  return {
    ...actual,
    useUploadAisleAssetsFlex: () => ({
      mutateAsync: mutateAsyncMock,
      isPending: false,
    }),
  };
});

describe('useAisleAssetUploadFlow', () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
    showSnackbarMock.mockReset();
    addEventListenerMock.mockClear();
  });

  it('exposes isUploadingPhotos while upload runs and registers beforeunload', async () => {
    mutateAsyncMock.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() =>
      useAisleAssetUploadFlow({ inventoryId: 'inv-1' })
    );

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
    let resolveFirst: (value: { assets: { id: string }[] }) => void = () => {};
    mutateAsyncMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        })
    );

    const { result } = renderHook(() =>
      useAisleAssetUploadFlow({ inventoryId: 'inv-1' })
    );

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

    expect(mutateAsyncMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst({ assets: [{ id: 'asset-1' }] });
    });

    await waitFor(() => {
      expect(result.current.isUploadingPhotos).toBe(false);
    });
  });

  it('does not open file picker while an upload is in progress', async () => {
    mutateAsyncMock.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() =>
      useAisleAssetUploadFlow({ inventoryId: 'inv-1' })
    );

    const clickSpy = vi.fn();
    const input = document.createElement('input');
    input.type = 'file';
    input.click = clickSpy;
    act(() => {
      result.current.fileInputRef.current = input;
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
    mutateAsyncMock.mockResolvedValue({ assets: [{ id: 'a1' }, { id: 'a2' }] });

    const { result } = renderHook(() =>
      useAisleAssetUploadFlow({ inventoryId: 'inv-1' })
    );

    await act(async () => {
      await result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      ]);
    });

    expect(result.current.isUploadingPhotos).toBe(false);
    expect(showSnackbarMock).toHaveBeenCalledWith('aisle.assets_uploaded_snackbar:2', 'success');
  });

  it('shows normalized error snackbar on failure and clears uploading state', async () => {
    mutateAsyncMock.mockRejectedValue(new Error('network'));

    const { result } = renderHook(() =>
      useAisleAssetUploadFlow({ inventoryId: 'inv-1' })
    );

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
