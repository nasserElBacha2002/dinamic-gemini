import '@testing-library/jest-dom/vitest';
import React, { type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../../src/theme';
import PhotoUploadProgressDialog from '../../src/components/ui/PhotoUploadProgressDialog';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('PhotoUploadProgressDialog', () => {
  it('shows progress copy while open', () => {
    render(
      <WithTheme>
        <PhotoUploadProgressDialog open />
      </WithTheme>
    );
    expect(screen.getByTestId('photo-upload-progress-dialog')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.dialogTitle')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.progress')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.waitBeforeLeaving')).toBeInTheDocument();
  });

  it('is hidden when closed', () => {
    render(
      <WithTheme>
        <PhotoUploadProgressDialog open={false} />
      </WithTheme>
    );
    expect(screen.queryByTestId('photo-upload-progress-dialog')).not.toBeInTheDocument();
  });

  it('stays open when Escape is pressed', () => {
    render(
      <WithTheme>
        <PhotoUploadProgressDialog open />
      </WithTheme>
    );
    const dialog = screen.getByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });
    expect(screen.getByTestId('photo-upload-progress-dialog')).toBeInTheDocument();
  });
});
