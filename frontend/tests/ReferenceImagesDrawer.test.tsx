import '@testing-library/jest-dom/vitest';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ReferenceImagesDrawer from '../src/components/ReferenceImagesDrawer';
import type { ReferenceImagesDrawerProps } from '../src/components/ReferenceImagesDrawer';

const { fetchInventoryVisualReferenceFileMock } = vi.hoisted(() => ({
  fetchInventoryVisualReferenceFileMock: vi.fn(),
}));

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    fetchInventoryVisualReferenceFile: fetchInventoryVisualReferenceFileMock,
  };
});

describe('ReferenceImagesDrawer', () => {
  const defaultItem = {
    id: 'ref-1',
    inventory_id: 'inv-1',
    filename: 'front-pallet.jpg',
    mime_type: 'image/jpeg',
    file_size: 1024,
    created_at: '2024-01-02T00:00:00Z',
  };

  function renderDrawer(overrides: Partial<ReferenceImagesDrawerProps> = {}) {
    const props: ReferenceImagesDrawerProps = {
      inventoryId: 'inv-1',
      open: true,
      onClose: vi.fn(),
      items: [],
      isLoading: false,
      errorMessage: null,
      onRetry: vi.fn(),
      onUpload: vi.fn().mockResolvedValue(undefined),
      isUploading: false,
      uploadError: null,
      onDelete: vi.fn().mockResolvedValue(undefined),
      isDeleting: false,
      deleteError: null,
      onReplace: vi.fn().mockResolvedValue(undefined),
      isReplacing: false,
      replaceError: null,
      ...overrides,
    };
    return {
      ...render(<ReferenceImagesDrawer {...props} />),
      props,
    };
  }

  beforeEach(() => {
    fetchInventoryVisualReferenceFileMock.mockReset();
    fetchInventoryVisualReferenceFileMock.mockResolvedValue({
      imageSrc: 'blob:test-preview',
      revoke: vi.fn(),
    });
  });

  it('renders empty state and real upload entry point', () => {
    renderDrawer();

    expect(screen.getByText(/empty message/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upload references/i })).toBeInTheDocument();
  });

  it('renders populated state with view action per reference', () => {
    renderDrawer({ items: [defaultItem] });

    expect(screen.getByText('front-pallet.jpg')).toBeInTheDocument();
    expect(
      screen.getByText(/management body/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^preview$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^replace$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument();
  });

  it('keeps long filenames readable via truncation-friendly title metadata', () => {
    const longFilename =
      'very-long-reference-image-name-for-inventory-front-pallet-label-example-2026-03-31-version-final.png';

    renderDrawer({
      items: [
        {
          id: 'ref-long',
          inventory_id: 'inv-1',
          filename: longFilename,
          mime_type: 'image/png',
          file_size: 740 * 1024,
          created_at: '2026-03-31T11:12:00Z',
        },
      ],
    });

    expect(screen.getByText(longFilename)).toBeInTheDocument();
    expect(screen.getByText(/subtitle uploaded/i)).toBeInTheDocument();
    expect(screen.getByText(/uploaded/i)).toBeInTheDocument();
  });

  it('passes selected files to the upload handler', () => {
    const onUpload = vi.fn().mockResolvedValue(undefined);

    renderDrawer({ onUpload });

    const file = new File(['abc'], 'ref.jpg', { type: 'image/jpeg' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload).toHaveBeenCalledWith([file]);
  });

  it('renders upload error from the parent mutation state', () => {
    renderDrawer({ uploadError: 'Upload failed for ref.jpg' });

    expect(screen.getByText('Upload failed for ref.jpg')).toBeInTheDocument();
  });

  it('renders preview error when preview loading fails', async () => {
    fetchInventoryVisualReferenceFileMock.mockRejectedValue(new Error('preview failed'));

    renderDrawer({ items: [defaultItem] });

    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        /Load results|something went wrong|preview failed|could not complete the operation/i
      );
    });
  });

  it('confirms delete and calls the delete handler', async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);

    renderDrawer({ items: [defaultItem], onDelete });

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: /delete title/i })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith('ref-1'));
  });

  it('passes the selected file to the replace handler', async () => {
    const onReplace = vi.fn().mockResolvedValue(undefined);

    renderDrawer({ items: [defaultItem], onReplace });

    const file = new File(['replacement'], 'replacement.jpg', { type: 'image/jpeg' });
    const inputs = document.querySelectorAll('input[type="file"]');
    const replaceInput = inputs[1] as HTMLInputElement;

    fireEvent.click(screen.getByRole('button', { name: /^replace$/i }));
    fireEvent.change(replaceInput, { target: { files: [file] } });

    await waitFor(() => expect(onReplace).toHaveBeenCalledWith('ref-1', file));
  });

  it('renders delete error from the parent mutation state', () => {
    renderDrawer({ deleteError: 'Delete failed for front-pallet.jpg' });

    expect(screen.getByText('Delete failed for front-pallet.jpg')).toBeInTheDocument();
  });

  it('renders replace error from the parent mutation state', () => {
    renderDrawer({ replaceError: 'Replace failed for front-pallet.jpg' });

    expect(screen.getByText('Replace failed for front-pallet.jpg')).toBeInTheDocument();
  });
});
