import '@testing-library/jest-dom/vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ImportSessionUpload from '../src/features/ingestionSessions/components/ImportSessionUpload';

const uploadMock = vi.fn();

vi.mock('../src/features/ingestionSessions/hooks/useUploadCaptureItems', () => ({
  useUploadCaptureItems: () => ({
    isPending: false,
    isUploading: false,
    isError: false,
    upload: uploadMock,
    retryFailed: vi.fn(),
    cancelUpload: vi.fn(),
    mutateAsync: uploadMock,
  }),
}));

vi.mock('../src/components/ui', async () => {
  const actual = await vi.importActual<typeof import('../src/components/ui')>('../src/components/ui');
  return {
    ...actual,
    PhotoUploadProgressDialog: () => null,
    useAppSnackbar: () => ({ showSnackbar: vi.fn() }),
  };
});

function makeFiles(n: number): File[] {
  return Array.from({ length: n }, (_, i) => new File([`x${i}`], `f${i}.jpg`, { type: 'image/jpeg' }));
}

describe('ImportSessionUpload file limits', () => {
  beforeEach(() => {
    uploadMock.mockReset();
  });

  it('allows selecting more than per-request max (auto-batch upstream)', async () => {
    uploadMock.mockResolvedValue({ uploadedCount: 12, failedCount: 0, cancelledCount: 0 });
    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    fireEvent.change(input, { target: { files: makeFiles(12) } });
    await waitFor(() => expect(uploadMock).toHaveBeenCalledTimes(1));
    expect(uploadMock.mock.calls[0][0].files).toHaveLength(12);
  });

  it('allows selecting MAX_FILES_PER_UPLOAD files', async () => {
    uploadMock.mockResolvedValue({ uploadedCount: 10, failedCount: 0, cancelledCount: 0 });
    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: makeFiles(10) } });
    await waitFor(() => expect(uploadMock).toHaveBeenCalled());
  });
});
