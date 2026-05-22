import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import SupplierReferenceImagesDrawer from '../src/features/clients/components/SupplierReferenceImagesDrawer';

vi.mock('../src/features/clients/hooks/useSupplierReferencePreview', () => ({
  useSupplierReferencePreview: () => ({
    loadPreview: vi.fn().mockResolvedValue({
      imageSrc: 'blob:test-supplier-preview',
      revoke: vi.fn(),
    }),
  }),
}));

vi.mock('../src/components/ui/useAppSnackbar', () => ({
  useAppSnackbar: () => ({
    showSnackbar: vi.fn(),
    closeSnackbar: vi.fn(),
  }),
}));

const defaultItem = {
  id: 'img-1',
  client_supplier_id: 'supplier-1',
  filename: 'proveedor-ref.jpg',
  mime_type: 'image/jpeg',
  file_size: 2048,
  created_at: '2024-06-01T12:00:00Z',
  updated_at: '2024-06-01T12:00:00Z',
};

function renderDrawer(
  overrides: Partial<React.ComponentProps<typeof SupplierReferenceImagesDrawer>> = {}
) {
  const props: React.ComponentProps<typeof SupplierReferenceImagesDrawer> = {
    clientId: 'client-1',
    supplierId: 'supplier-1',
    supplierName: 'Proveedor Test',
    open: true,
    onClose: vi.fn(),
    items: [],
    isLoading: false,
    onUpload: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { ...render(<SupplierReferenceImagesDrawer {...props} />), props };
}

describe('SupplierReferenceImagesDrawer', () => {
  it('accepts label and description, calls onUpload with files and metadata, clears fields on success', async () => {
    const { props } = renderDrawer();

    fireEvent.change(screen.getByLabelText(/^Etiqueta$/), { target: { value: 'Etiqueta uno' } });
    fireEvent.change(screen.getByLabelText(/^Descripción$/), { target: { value: 'Desc uno' } });

    const file = new File(['x'], 'upload.jpg', { type: 'image/jpeg' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.multiple).toBe(false);

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(props.onUpload).toHaveBeenCalledWith({
        files: [file],
        label: 'Etiqueta uno',
        description: 'Desc uno',
      });
    });

    expect(screen.getByLabelText(/^Etiqueta$/)).toHaveValue('');
    expect(screen.getByLabelText(/^Descripción$/)).toHaveValue('');
  });

  it('does not clear label and description when onUpload rejects', async () => {
    const onUpload = vi.fn().mockRejectedValue(new Error('upload failed'));
    renderDrawer({ onUpload });

    fireEvent.change(screen.getByLabelText(/^Etiqueta$/), { target: { value: 'Keep me' } });
    fireEvent.change(screen.getByLabelText(/^Descripción$/), { target: { value: 'Keep desc' } });

    const file = new File(['x'], 'upload.jpg', { type: 'image/jpeg' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onUpload).toHaveBeenCalled());

    expect(screen.getByLabelText(/^Etiqueta$/)).toHaveValue('Keep me');
    expect(screen.getByLabelText(/^Descripción$/)).toHaveValue('Keep desc');
  });

  it('renders an existing image and confirms delete calls onDelete with image id', async () => {
    const { props } = renderDrawer({ items: [defaultItem] });

    expect(screen.getByText('proveedor-ref.jpg')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Eliminar imagen$/ }));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/proveedor-ref\.jpg/)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: /^Eliminar imagen$/ }));

    await waitFor(() => expect(props.onDelete).toHaveBeenCalledWith('img-1'));
  });
});
