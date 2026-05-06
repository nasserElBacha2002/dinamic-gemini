/**
 * Interaction state for ManagedImageAssetsDrawer — close drawer must clear nested dialogs.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ManagedImageAssetsDrawer from '../src/components/imageAssets/ManagedImageAssetsDrawer';
import type { ManagedImageAssetItem } from '../src/components/imageAssets/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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

describe('ManagedImageAssetsDrawer', () => {
  it('does not call onFetchPreview when previewBlockedMessage returns a reason', () => {
    const onFetchPreview = vi.fn().mockResolvedValue({ imageSrc: 'blob:x', revoke: () => {} });
    render(
      <ManagedImageAssetsDrawer
        open
        onClose={() => {}}
        copy={minimalCopy}
        items={oneItem}
        getItemSubtitle={() => 'sub'}
        isLoading={false}
        onFetchPreview={onFetchPreview}
        onDelete={vi.fn()}
        formatDeleteConfirm={(n) => `confirm-${n}`}
        previewBlockedMessage={() => 'blocked-by-type'}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /vista previa|preview/i }));
    expect(onFetchPreview).not.toHaveBeenCalled();
  });

  it('clears delete confirmation when drawer closes', () => {
    const onClose = vi.fn();
    function Harness(props: { open: boolean }) {
      return (
        <ManagedImageAssetsDrawer
          open={props.open}
          onClose={onClose}
          copy={minimalCopy}
          items={oneItem}
          getItemSubtitle={() => 'sub'}
          isLoading={false}
          onFetchPreview={vi.fn().mockResolvedValue({ imageSrc: 'https://example.com/x.png' })}
          onDelete={vi.fn()}
          formatDeleteConfirm={(n) => `confirm-${n}`}
        />
      );
    }
    const { rerender } = render(<Harness open />);
    fireEvent.click(screen.getByRole('button', { name: /eliminar|delete/i }));
    expect(screen.getByText('confirm-x.jpg')).toBeTruthy();
    rerender(<Harness open={false} />);
    expect(screen.queryByText('confirm-x.jpg')).toBeNull();
  });
});
