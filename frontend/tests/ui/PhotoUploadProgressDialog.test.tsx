import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PhotoUploadProgressDialog from '../../src/components/ui/PhotoUploadProgressDialog';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('PhotoUploadProgressDialog', () => {
  it('shows progress copy while open', () => {
    render(<PhotoUploadProgressDialog open />);
    expect(screen.getByTestId('photo-upload-progress-dialog')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.dialogTitle')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.progress')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.waitBeforeLeaving')).toBeInTheDocument();
  });

  it('is hidden when closed', () => {
    render(<PhotoUploadProgressDialog open={false} />);
    expect(screen.queryByTestId('photo-upload-progress-dialog')).not.toBeInTheDocument();
  });
});
