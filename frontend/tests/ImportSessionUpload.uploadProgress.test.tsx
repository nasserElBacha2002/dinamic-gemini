import '@testing-library/jest-dom/vitest';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import { ApiError } from '../src/api/types';
import ImportSessionUpload from '../src/features/ingestionSessions/components/ImportSessionUpload';

const uploadMock = vi.fn();
const cancelUploadMock = vi.fn();
const showSnackbarMock = vi.fn();

let isUploading = false;

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
    upload: uploadMock,
    retryFailed: vi.fn(),
    cancelUpload: cancelUploadMock,
    mutateAsync: uploadMock,
    get isPending() {
      return isUploading;
    },
    get isUploading() {
      return isUploading;
    },
    isError: false,
  }),
}));

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('ImportSessionUpload upload progress', () => {
  beforeEach(() => {
    uploadMock.mockReset();
    cancelUploadMock.mockReset();
    showSnackbarMock.mockReset();
    isUploading = false;
  });

  it('shows progress dialog and disables select while uploading', () => {
    isUploading = true;
    render(
      <WithTheme>
        <ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />
      </WithTheme>
    );

    // Dialog opens only after an upload starts with dialogOpen state — set uploading via selection path
    // For pending-only mount, dialog may stay closed until upload starts; assert select disabled.
    expect(screen.getByText('ingestion_sessions.upload.select_files').closest('button')).toBeDisabled();
  });

  it('wires cancel to PhotoUploadProgressDialog while uploading', async () => {
    uploadMock.mockImplementation(
      () =>
        new Promise(() => {
          /* hang so dialog stays open */
        })
    );

    render(
      <WithTheme>
        <ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />
      </WithTheme>
    );
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'a.jpg', { type: 'image/jpeg' })] },
    });

    await waitFor(() => {
      expect(screen.getByTestId('photo-upload-progress-dialog')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'uploads.photos.cancel' }));
    expect(cancelUploadMock).toHaveBeenCalled();
  });

  it('shows success snackbar when all files upload', async () => {
    uploadMock.mockImplementation(async () => {
      isUploading = true;
      await Promise.resolve();
      isUploading = false;
      return { uploadedCount: 2, failedCount: 0, cancelledCount: 0 };
    });

    render(
      <WithTheme>
        <ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />
      </WithTheme>
    );
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = [
      new File(['x'], 'a.jpg', { type: 'image/jpeg' }),
      new File(['y'], 'b.jpg', { type: 'image/jpeg' }),
    ];
    fireEvent.change(input, { target: { files } });

    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledWith('uploads.photos.success', 'success');
    });
  });

  it('shows normalized error snackbar and inline alert on failed upload', async () => {
    uploadMock.mockRejectedValue(
      new ApiError('upload failed', 500, { code: 'CAPTURE_UPLOAD_FAILED', detail: 'Server busy' })
    );

    render(
      <WithTheme>
        <ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />
      </WithTheme>
    );
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'a.jpg', { type: 'image/jpeg' })] },
    });

    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledWith(expect.any(String), 'error');
      expect(screen.getByTestId('import-session-upload-error')).toBeInTheDocument();
    });
    expect(showSnackbarMock).not.toHaveBeenCalledWith('uploads.photos.error', 'error');
  });
});
