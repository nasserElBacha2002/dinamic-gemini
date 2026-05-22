import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ManagedImageAssetsDrawer from '../src/components/imageAssets/ManagedImageAssetsDrawer';

vi.mock('../src/components/ui/useAppSnackbar', () => ({
  useAppSnackbar: () => ({
    showSnackbar: vi.fn(),
    closeSnackbar: vi.fn(),
  }),
}));

const baseCopy = {
  closeAria: 'Close drawer',
  contextOverline: 'Context',
  title: 'Assets',
  managementTitle: 'Management',
  managementBody: 'Manage assets here.',
  uploadButton: 'Upload',
  emptyTitle: 'Empty',
  emptyMessage: 'No items',
  preview: 'Preview',
  delete: 'Delete item',
  deleteTitle: 'Confirm delete',
  deleteFallbackName: 'this item',
  imagePreviewTitle: 'Image preview',
  imagePreviewAlt: 'preview alt',
};

function renderDrawer(overrides: Partial<React.ComponentProps<typeof ManagedImageAssetsDrawer>> = {}) {
  const props: React.ComponentProps<typeof ManagedImageAssetsDrawer> = {
    open: true,
    onClose: vi.fn(),
    copy: baseCopy,
    items: [],
    getItemSubtitle: () => 'subtitle',
    isLoading: false,
    onFetchPreview: vi.fn().mockResolvedValue({ imageSrc: 'blob:test-preview', revoke: vi.fn() }),
    onDelete: vi.fn().mockResolvedValue(undefined),
    formatDeleteConfirm: (name) => `Delete ${name}?`,
    ...overrides,
  };
  return { ...render(<ManagedImageAssetsDrawer {...props} />), props };
}

describe('ManagedImageAssetsDrawer preview revoke', () => {
  it('calls revoke when the preview dialog closes', async () => {
    const revoke = vi.fn();
    const onFetchPreview = vi.fn().mockResolvedValue({
      imageSrc: 'blob:preview-1',
      revoke,
    });

    renderDrawer({
      items: [
        {
          id: 'a',
          filename: 'one.jpg',
          mime_type: 'image/jpeg',
          file_size: 10,
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
      onFetchPreview,
    });

    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));

    await waitFor(() => expect(onFetchPreview).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: /^Close preview$/i }));

    await waitFor(() => expect(revoke).toHaveBeenCalledTimes(1));
  });

  it('revokes the previous preview when opening a different item', async () => {
    const revoke1 = vi.fn();
    const revoke2 = vi.fn();
    let n = 0;
    const onFetchPreview = vi.fn().mockImplementation(async () => {
      n += 1;
      return n === 1
        ? { imageSrc: 'blob:first', revoke: revoke1 }
        : { imageSrc: 'blob:second', revoke: revoke2 };
    });

    renderDrawer({
      items: [
        {
          id: 'a',
          filename: 'one.jpg',
          mime_type: 'image/jpeg',
          file_size: 10,
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'b',
          filename: 'two.jpg',
          mime_type: 'image/jpeg',
          file_size: 11,
          created_at: '2024-01-02T00:00:00Z',
        },
      ],
      onFetchPreview,
    });

    const previewButtons = screen.getAllByRole('button', { name: /^Preview$/i });
    fireEvent.click(previewButtons[0]);

    await waitFor(() => expect(onFetchPreview).toHaveBeenCalledTimes(1));

    fireEvent.click(previewButtons[1]);

    await waitFor(() => expect(onFetchPreview).toHaveBeenCalledTimes(2));

    expect(revoke1).toHaveBeenCalledTimes(1);
  });

  it('revokes an active preview on unmount', async () => {
    const revoke = vi.fn();
    const onFetchPreview = vi.fn().mockResolvedValue({
      imageSrc: 'blob:stay-open',
      revoke,
    });

    const { unmount } = renderDrawer({
      items: [
        {
          id: 'a',
          filename: 'one.jpg',
          mime_type: 'image/jpeg',
          file_size: 10,
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
      onFetchPreview,
    });

    fireEvent.click(screen.getByRole('button', { name: /^Preview$/i }));

    await waitFor(() => expect(onFetchPreview).toHaveBeenCalled());

    unmount();

    expect(revoke).toHaveBeenCalledTimes(1);
  });
});
