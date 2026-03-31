import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ReferenceImagesDrawer from '../src/components/ReferenceImagesDrawer';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    fetchInventoryVisualReferenceFile: vi.fn().mockResolvedValue({
      imageSrc: 'blob:test-preview',
      revoke: vi.fn(),
    }),
  };
});

describe('ReferenceImagesDrawer', () => {
  it('renders empty state and real upload entry point', () => {
    render(
      <ReferenceImagesDrawer
        inventoryId="inv-1"
        open
        onClose={vi.fn()}
        items={[]}
        isLoading={false}
        errorMessage={null}
        onRetry={vi.fn()}
        onUpload={vi.fn().mockResolvedValue(undefined)}
        isUploading={false}
        uploadError={null}
      />,
    );

    expect(screen.getByText(/no reference images uploaded yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upload references/i })).toBeInTheDocument();
    expect(screen.getByText(/replace and delete actions are not exposed yet/i)).toBeInTheDocument();
  });

  it('renders populated state with view action per reference', () => {
    render(
      <ReferenceImagesDrawer
        inventoryId="inv-1"
        open
        onClose={vi.fn()}
        items={[
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ]}
        isLoading={false}
        errorMessage={null}
        onRetry={vi.fn()}
        onUpload={vi.fn().mockResolvedValue(undefined)}
        isUploading={false}
        uploadError={null}
      />,
    );

    expect(screen.getByText('front-pallet.jpg')).toBeInTheDocument();
    expect(
      screen.getByText(/reference images are used for future processing runs only\./i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^view$/i })).toBeInTheDocument();
  });

  it('passes selected files to the upload handler', () => {
    const onUpload = vi.fn().mockResolvedValue(undefined);

    render(
      <ReferenceImagesDrawer
        inventoryId="inv-1"
        open
        onClose={vi.fn()}
        items={[]}
        isLoading={false}
        errorMessage={null}
        onRetry={vi.fn()}
        onUpload={onUpload}
        isUploading={false}
        uploadError={null}
      />,
    );

    const file = new File(['abc'], 'ref.jpg', { type: 'image/jpeg' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload).toHaveBeenCalledWith([file]);
  });
});
