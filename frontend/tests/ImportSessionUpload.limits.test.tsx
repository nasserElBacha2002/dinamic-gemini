import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ImportSessionUpload from '../src/features/ingestionSessions/components/ImportSessionUpload';
import { MAX_FILES_PER_UPLOAD } from '../src/constants/uploads';

const mutateAsyncMock = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../src/features/ingestionSessions/hooks/useUploadCaptureItems', () => ({
  useUploadCaptureItems: () => ({
    mutateAsync: mutateAsyncMock,
    isPending: false,
    isError: false,
  }),
}));

function makeFiles(count: number): File[] {
  return Array.from({ length: count }, (_, i) => new File(['x'], `f${i}.jpg`, { type: 'image/jpeg' }));
}

describe('ImportSessionUpload file limits', () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
  });

  it('blocks selecting more than MAX_FILES_PER_UPLOAD files', async () => {
    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = makeFiles(MAX_FILES_PER_UPLOAD + 1);
    fireEvent.change(input, { target: { files } });
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(mutateAsyncMock).not.toHaveBeenCalled();
  });

  it('blocks dropping more than MAX_FILES_PER_UPLOAD files', async () => {
    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);
    const dropZone = screen.getByText('ingestion_sessions.upload.title').closest('.MuiPaper-root');
    expect(dropZone).toBeTruthy();
    const files = makeFiles(MAX_FILES_PER_UPLOAD + 1);
    const dataTransfer = {
      files: Object.assign(files, {
        item: (index: number) => files[index] ?? null,
      }),
      types: ['Files'],
    };
    fireEvent.drop(dropZone!, { dataTransfer });
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(mutateAsyncMock).not.toHaveBeenCalled();
  });

  it('allows selecting MAX_FILES_PER_UPLOAD files', async () => {
    mutateAsyncMock.mockResolvedValue({ uploadedCount: MAX_FILES_PER_UPLOAD, failedCount: 0 });
    render(<ImportSessionUpload inventoryId="inv-1" sessionId="sess-1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: makeFiles(MAX_FILES_PER_UPLOAD) } });
    await waitFor(() => {
      expect(mutateAsyncMock).toHaveBeenCalled();
    });
  });
});
