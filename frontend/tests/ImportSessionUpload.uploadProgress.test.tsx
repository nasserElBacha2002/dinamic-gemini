import '@testing-library/jest-dom/vitest';
import React, { type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import { ApiError } from '../src/api/types';
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

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('ImportSessionUpload upload progress', () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
    showSnackbarMock.mockReset();
    isPending = false;
  });

  it('shows progress dialog and disables select while pending', () => {
    isPending = true;
    render(
      <WithTheme>
        <ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />
      </WithTheme>
    );

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
    expect(screen.queryByTestId('photo-upload-progress-dialog')).not.toBeInTheDocument();
  });

  it('shows normalized error snackbar and inline alert on failed upload', async () => {
    mutateAsyncMock.mockRejectedValue(
      new ApiError('upload failed', 500, { code: 'CAPTURE_UPLOAD_FAILED', message: 'Server busy' })
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
