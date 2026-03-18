import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CreateInventoryDialog from '../src/components/CreateInventoryDialog';

const mockUpload = vi.fn();
vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    uploadInventoryVisualReferences: (inventoryId: string, files: File[]) =>
      mockUpload(inventoryId, files),
  };
});

function renderDialog(props?: Partial<React.ComponentProps<typeof CreateInventoryDialog>>) {
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
    />
  );
  return { onClose, onSuccess, onError, createInventoryFn };
}

describe('CreateInventoryDialog (visual references step)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Make object URLs deterministic and assertable for lifecycle tests.
    let i = 0;
    URL.createObjectURL = vi.fn(() => `blob:test-${++i}`);
    URL.revokeObjectURL = vi.fn();
  });

  it('allows continuing to step 2 and skipping upload', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();

    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    expect(screen.getByText(/visual reference images/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /skip this step/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    expect(mockUpload).not.toHaveBeenCalled();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('validates max 3 files and invalid mime type', async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    const input = screen.getByLabelText(/select visual reference images/i) as HTMLInputElement;
    const bad = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [bad] } });
    expect(screen.getByText(/only jpg/i)).toBeInTheDocument();

    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    const f2 = new File(['b'], 'b.png', { type: 'image/png' });
    const f3 = new File(['c'], 'c.webp', { type: 'image/webp' });
    const f4 = new File(['d'], 'd.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1, f2, f3] } });
    expect(screen.getByText('a.jpg')).toBeInTheDocument();
    expect(screen.getByText('b.png')).toBeInTheDocument();
    expect(screen.getByText('c.webp')).toBeInTheDocument();

    fireEvent.change(input, { target: { files: [f4] } });
    expect(screen.getByText('You can upload up to 3 images.')).toBeInTheDocument();
  });

  it('creates inventory then uploads references (in order)', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();
    mockUpload.mockResolvedValue({ items: [] });

    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    const input = screen.getByLabelText(/select visual reference images/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });

    fireEvent.click(screen.getByRole('button', { name: /create inventory and upload references/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    expect(mockUpload).toHaveBeenCalledWith('inv-1', [f1]);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('surfaces upload failure after inventory creation', async () => {
    const { createInventoryFn, onError } = renderDialog();
    mockUpload.mockRejectedValue(new Error('upload failed'));

    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    const input = screen.getByLabelText(/select visual reference images/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });

    fireEvent.click(screen.getByRole('button', { name: /create inventory and upload references/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText(/inventory created, but visual reference upload failed/i)).toBeInTheDocument()
    );
    // Partial failure should not bubble as a "create failed" page-level error.
    expect(onError).not.toHaveBeenCalledWith(expect.stringMatching(/visual reference upload failed/i));
  });

  it('after upload failure, retry does not create a second inventory', async () => {
    const { createInventoryFn } = renderDialog();
    mockUpload.mockRejectedValueOnce(new Error('upload failed'));
    mockUpload.mockResolvedValueOnce({ items: [] });

    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    const input = screen.getByLabelText(/select visual reference images/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [f1] } });

    fireEvent.click(screen.getByRole('button', { name: /create inventory and upload references/i }));
    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry upload/i })).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', { name: /retry upload/i }));
    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(2));
    // Key assertion: inventory creation is NOT retriggered on retry.
    expect(createInventoryFn).toHaveBeenCalledTimes(1);
  });

  it('revokes object URLs when removing and closing', async () => {
    const { onClose } = renderDialog();

    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    const input = screen.getByLabelText(/select visual reference images/i) as HTMLInputElement;
    const f1 = new File(['a'], 'a.jpg', { type: 'image/jpeg' });
    const f2 = new File(['b'], 'b.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [f1, f2] } });

    // remove first file -> revoke its preview URL
    fireEvent.click(screen.getByRole('button', { name: /remove a\.jpg/i }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-1');

    // close dialog -> revoke remaining preview URL
    fireEvent.click(screen.getByRole('button', { name: /back/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-2');
  });
});

