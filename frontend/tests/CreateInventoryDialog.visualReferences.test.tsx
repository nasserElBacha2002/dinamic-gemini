import '@testing-library/jest-dom/vitest';
import React from 'react';
import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CreateInventoryDialog from '../src/components/CreateInventoryDialog';

const mockUpload = vi.fn();
const mockUseClients = vi.fn();
vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    uploadInventoryVisualReferences: (inventoryId: string, files: File[]) => mockUpload(inventoryId, files),
  };
});
vi.mock('../src/hooks/useClients', () => ({
  useClients: (...args: unknown[]) => mockUseClients(...args),
}));

function renderDialog(props?: Partial<ComponentProps<typeof CreateInventoryDialog>>) {
  const onClose = vi.fn();
  const onSuccess = vi.fn();
  const onError = vi.fn();
  const createInventoryFn = vi.fn().mockResolvedValue({
    id: 'inv-1',
    name: 'My inv',
    status: 'draft',
    created_at: null,
  });
  render(
    <CreateInventoryDialog
      open
      onClose={onClose}
      onSuccess={onSuccess}
      onError={onError}
      createInventoryFn={createInventoryFn}
      {...props}
    />,
  );
  return { onClose, onSuccess, onError, createInventoryFn };
}

describe('CreateInventoryDialog (reference images step)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseClients.mockReturnValue({
      data: {
        items: [
          { id: 'client-1', name: 'Cliente Uno', status: 'active', created_at: '', updated_at: '' },
          { id: 'client-2', name: 'Cliente Dos', status: 'active', created_at: '', updated_at: '' },
        ],
      },
      isLoading: false,
      isError: false,
    });
    // Make object URLs deterministic and assertable for lifecycle tests.
    let i = 0;
    URL.createObjectURL = vi.fn(() => `blob:test-${++i}`);
    URL.revokeObjectURL = vi.fn();
  });

  it('allows continuing to step 2 and skipping upload', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();

    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    expect(screen.getByRole('heading', { name: /referencias visuales|reference step title/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /crear sin referencias|create without refs/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    expect(createInventoryFn).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'My inv', processing_mode: 'production' }),
    );
    expect(mockUpload).not.toHaveBeenCalled();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('renders client selector with default legacy option', () => {
    renderDialog();
    const selector = screen.getByRole('combobox', { name: /^cliente$/i });
    expect(selector).toBeInTheDocument();
    expect(screen.getByText(/seleccioná el cliente al que pertenece este inventario/i)).toBeInTheDocument();
    fireEvent.mouseDown(selector);
    expect(screen.getByRole('option', { name: /sin cliente/i })).toBeInTheDocument();
  });

  it('disables client selector while clients are loading', () => {
    mockUseClients.mockReturnValueOnce({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    renderDialog();
    expect(screen.getByRole('combobox', { name: /^cliente$/i })).toHaveAttribute('aria-disabled', 'true');
  });

  it('shows helper when clients fail to load', () => {
    mockUseClients.mockReturnValueOnce({
      data: undefined,
      isLoading: false,
      isError: true,
    });
    renderDialog();
    expect(screen.getByText(/no se pudieron cargar los clientes/i)).toBeInTheDocument();
  });

  it('shows helper when no clients exist', () => {
    mockUseClients.mockReturnValueOnce({
      data: { items: [] },
      isLoading: false,
      isError: false,
    });
    renderDialog();
    expect(screen.getByText(/no hay clientes disponibles/i)).toBeInTheDocument();
  });

  it('sends processing_mode test when Test mode is selected', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();

    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'Lab inv' } });
    fireEvent.click(screen.getByRole('button', { name: /^prueba$/i }));
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    fireEvent.click(screen.getByRole('button', { name: /crear sin referencias|create without refs/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    expect(createInventoryFn).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Lab inv', processing_mode: 'test' }),
    );
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('sends client_id when a client is selected', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^cliente$/i }));
    fireEvent.click(screen.getByRole('option', { name: /cliente dos/i }));
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));
    fireEvent.click(screen.getByRole('button', { name: /crear sin referencias|create without refs/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    expect(createInventoryFn).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'My inv', processing_mode: 'production', client_id: 'client-2' }),
    );
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('does not send empty client_id when no client is selected', async () => {
    const { createInventoryFn } = renderDialog();
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'No client' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));
    fireEvent.click(screen.getByRole('button', { name: /crear sin referencias|create without refs/i }));
    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    const payload = createInventoryFn.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.client_id).toBeUndefined();
  });

  it('validates max 3 files and invalid mime type', async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    const input = screen.getByLabelText(/elegir archivos|select files/i) as HTMLInputElement;
    const bad = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [bad] } });
    expect(screen.getByText(/solo se permiten|files type error/i)).toBeInTheDocument();

    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    const f2 = new File(['b'], 'b.png', { type: 'image/png' });
    const f3 = new File(['c'], 'c.webp', { type: 'image/webp' });
    const f4 = new File(['d'], 'd.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1, f2, f3] } });
    expect(screen.getByText('a.jpg')).toBeInTheDocument();
    expect(screen.getByText('b.png')).toBeInTheDocument();
    expect(screen.getByText('c.webp')).toBeInTheDocument();

    fireEvent.change(input, { target: { files: [f4] } });
    expect(screen.getByText(/como máximo|max files error/i)).toBeInTheDocument();
  });

  it('creates inventory then uploads references (in order)', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();
    mockUpload.mockResolvedValue({ items: [] });

    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    const input = screen.getByLabelText(/elegir archivos|select files/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });

    expect(screen.getByRole('button', { name: /crear y subir|create and upload/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /crear y subir|create and upload/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    expect(mockUpload).toHaveBeenCalledWith('inv-1', [f1]);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('surfaces upload failure after inventory creation', async () => {
    const { createInventoryFn, onError } = renderDialog();
    mockUpload.mockRejectedValue(new Error('upload failed'));

    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    const input = screen.getByLabelText(/elegir archivos|select files/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });

    fireEvent.click(screen.getByRole('button', { name: /crear y subir|create and upload/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    // Upload error surfaces inline + enables retry (inventory already created).
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /reintentar subida|retry upload/i })).toBeInTheDocument(),
    );
    // Partial failure should not bubble as a "create failed" page-level error.
    expect(onError).not.toHaveBeenCalledWith(expect.stringMatching(/reference image upload failed/i));
  });

  it('after upload failure, retry does not create a second inventory', async () => {
    const { createInventoryFn } = renderDialog();
    mockUpload.mockRejectedValueOnce(new Error('upload failed'));
    mockUpload.mockResolvedValueOnce({ items: [] });

    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    const input = screen.getByLabelText(/elegir archivos|select files/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });

    fireEvent.click(screen.getByRole('button', { name: /crear y subir|create and upload/i }));
    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /reintentar subida|retry upload/i })).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', { name: /reintentar subida|retry upload/i }));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(2));
    // Key assertion: inventory creation is NOT retriggered on retry.
    expect(createInventoryFn).toHaveBeenCalledTimes(1);
  });

  it('revokes object URLs when removing and closing', async () => {
    const { onClose } = renderDialog();

    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    const input = screen.getByLabelText(/elegir archivos|select files/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    const f2 = new File(['b'], 'b.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [f1, f2] } });

    // remove first file -> revoke its preview URL
    fireEvent.click(screen.getAllByRole('button', { name: /quitar a\.jpg|remove file a11y/i })[0]);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-1');

    // close dialog -> revoke remaining preview URL
    fireEvent.click(screen.getByRole('button', { name: /back|volver/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-2');
  });

  it('accepts drag-and-drop into dropzone', async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    const dropzone = screen.getByRole('region', {
      name: /zona para imágenes de referencia|reference dropzone/i,
    });
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.drop(dropzone, { dataTransfer: { files: [f1] } });
    expect(screen.getByText('a.jpg')).toBeInTheDocument();
    expect(screen.getByText(/1 \/ 3 archivos|selected ratio/i)).toBeInTheDocument();
  });

  it('Step 2 primary CTA label is context-aware', async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue|continuar/i }));

    // no selected files → Create inventory action
    expect(
      screen.getByRole('button', { name: /^crear inventario$|^create inventory action$/i }),
    ).toBeInTheDocument();

    // select a file → Create inventory and upload references
    const input = screen.getByLabelText(/elegir archivos|select files/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });
    expect(screen.getByRole('button', { name: /crear y subir|create and upload/i })).toBeInTheDocument();
  });
});

