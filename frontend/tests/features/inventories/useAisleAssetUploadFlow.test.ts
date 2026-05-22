import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useAisleAssetUploadFlow } from '../../../src/features/inventories/hooks/useAisleAssetUploadFlow';

const mutateAsyncMock = vi.fn();
const showSnackbarMock = vi.fn();
const addEventListenerMock = vi.spyOn(window, 'addEventListener');

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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

  it('shows success snackbar after upload completes', async () => {
    mutateAsyncMock.mockResolvedValue({ assets: [{ id: 'asset-1' }] });

    const { result } = renderHook(() =>
      useAisleAssetUploadFlow({ inventoryId: 'inv-1' })
    );

    await act(async () => {
      await result.current.handleFilesSelectedForAisle('aisle-1', [
        new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      ]);
    });

    expect(result.current.isUploadingPhotos).toBe(false);
    expect(showSnackbarMock).toHaveBeenCalledWith('uploads.photos.success', 'success');
  });

  it('shows error snackbar and clears uploading state on failure', async () => {
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
