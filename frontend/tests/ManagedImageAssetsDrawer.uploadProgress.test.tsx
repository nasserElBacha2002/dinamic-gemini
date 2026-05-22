import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ManagedImageAssetsDrawer from '../src/components/imageAssets/ManagedImageAssetsDrawer';
import type { ManagedImageAssetItem } from '../src/components/imageAssets/types';

const showSnackbarMock = vi.fn();

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

const minimalCopy = {
  closeAria: 'close',
  contextOverline: 'ctx',
  title: 'Title',
  subtitle: 'Sub',
  managementTitle: 'Mgmt',
  managementBody: 'Body',
  uploadButton: 'Upload',
  emptyTitle: 'Empty',
  emptyMessage: 'Empty msg',
  preview: 'Preview',
  delete: 'Delete',
  deleteTitle: 'DeleteTitle',
  deleteFallbackName: 'file',
  imagePreviewTitle: 'Img',
  imagePreviewAlt: 'Alt',
};

const oneItem: ManagedImageAssetItem[] = [
  {
    id: 'a1',
    filename: 'x.jpg',
    mime_type: 'image/jpeg',
    file_size: 100,
    created_at: '2024-01-01T00:00:00Z',
  },
];

describe('ManagedImageAssetsDrawer upload progress', () => {
  beforeEach(() => {
    showSnackbarMock.mockReset();
  });

  it('shows blocking dialog and disables upload while isUploading', () => {
    render(
      <ManagedImageAssetsDrawer
        open
        onClose={() => {}}
        copy={minimalCopy}
        items={oneItem}
        getItemSubtitle={() => 'sub'}
        isLoading={false}
        onFetchPreview={vi.fn().mockResolvedValue({ imageSrc: 'https://example.com/x.png' })}
        showUpload
        onUpload={vi.fn().mockResolvedValue(undefined)}
        isUploading
      />
    );

    expect(screen.getByTestId('photo-upload-progress-dialog')).toBeInTheDocument();
    expect(screen.getByText('uploads.photos.progress')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /uploads\.photos\.uploadingButton/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'close' })).toBeDisabled();
  });

  it('prevents drawer close while uploading', () => {
    const onClose = vi.fn();
    render(
      <ManagedImageAssetsDrawer
        open
        onClose={onClose}
        copy={minimalCopy}
        items={oneItem}
        getItemSubtitle={() => 'sub'}
        isLoading={false}
        onFetchPreview={vi.fn().mockResolvedValue({ imageSrc: 'https://example.com/x.png' })}
        showUpload
        onUpload={vi.fn().mockResolvedValue(undefined)}
        isUploading
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'close' }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('shows success snackbar after upload completes', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined);
    render(
      <ManagedImageAssetsDrawer
        open
        onClose={() => {}}
        copy={minimalCopy}
        items={oneItem}
        getItemSubtitle={() => 'sub'}
        isLoading={false}
        onFetchPreview={vi.fn().mockResolvedValue({ imageSrc: 'https://example.com/x.png' })}
        showUpload
        onUpload={onUpload}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(onUpload).toHaveBeenCalled();
      expect(showSnackbarMock).toHaveBeenCalledWith('uploads.photos.success', 'success');
    });
  });

  it('does not render progress dialog when showProgressDialog is false', () => {
    render(
      <ManagedImageAssetsDrawer
        open
        onClose={() => {}}
        copy={minimalCopy}
        items={oneItem}
        getItemSubtitle={() => 'sub'}
        isLoading={false}
        onFetchPreview={vi.fn().mockResolvedValue({ imageSrc: 'https://example.com/x.png' })}
        showUpload
        onUpload={vi.fn().mockResolvedValue(undefined)}
        isUploading
        showProgressDialog={false}
      />
    );

    expect(screen.queryByTestId('photo-upload-progress-dialog')).not.toBeInTheDocument();
  });

  it('does not start a second upload while already uploading', async () => {
    const onUpload = vi.fn().mockImplementation(() => new Promise(() => {}));
    render(
      <ManagedImageAssetsDrawer
        open
        onClose={() => {}}
        copy={minimalCopy}
        items={oneItem}
        getItemSubtitle={() => 'sub'}
        isLoading={false}
        onFetchPreview={vi.fn().mockResolvedValue({ imageSrc: 'https://example.com/x.png' })}
        showUpload
        onUpload={onUpload}
        isUploading
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onUpload).not.toHaveBeenCalled();
  });
});
