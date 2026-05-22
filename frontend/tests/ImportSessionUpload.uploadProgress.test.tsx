import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ImportSessionUpload from '../src/features/ingestionSessions/components/ImportSessionUpload';

const mutateAsyncMock = vi.fn();
const showSnackbarMock = vi.fn();

let isPending = false;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../src/components/ui/useAppSnackbar', () => ({
  useAppSnackbar: () => ({
    showSnackbar: showSnackbarMock,
    closeSnackbar: vi.fn(),
  }),
}));

vi.mock('../src/features/ingestionSessions/hooks/useUploadCaptureItems', () => ({
  useUploadCaptureItems: () => ({
    mutateAsync: mutateAsyncMock,
    get isPending() {
      return isPending;
    },
    isError: false,
  }),
}));

describe('ImportSessionUpload upload progress', () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
    showSnackbarMock.mockReset();
    isPending = false;
  });

  it('shows progress dialog and disables select while pending', () => {
    isPending = true;
    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);

    expect(screen.getByTestId('photo-upload-progress-dialog')).toBeInTheDocument();
    expect(screen.getByText('ingestion_sessions.upload.select_files').closest('button')).toBeDisabled();
  });

  it('shows success snackbar when all files upload', async () => {
    mutateAsyncMock.mockImplementation(async () => {
      isPending = true;
      await Promise.resolve();
      isPending = false;
      return { uploadedCount: 2, failedCount: 0 };
    });

    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = [
      new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      new File(['y'], 'b.jpg', { type: 'image/jpeg' }),
    ];
    fireEvent.change(input, { target: { files } });

    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledWith('uploads.photos.success', 'success');
    });
    expect(screen.queryByTestId('photo-upload-progress-dialog')).not.toBeInTheDocument();
  });
});
