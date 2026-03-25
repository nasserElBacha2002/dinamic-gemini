import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CreateInventoryDialog from '../src/components/CreateInventoryDialog';

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

describe('CreateInventoryDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders name field and actions', () => {
    renderDialog();
    expect(screen.getByRole('heading', { name: /create inventory/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/inventory name/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create inventory/i })).toBeInTheDocument();
  });

  it('validates required name', async () => {
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /create inventory/i }));
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
  });

  it('submits and calls onSuccess', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();
    fireEvent.change(screen.getByLabelText(/inventory name/i), { target: { value: 'My inv' } });
    fireEvent.click(screen.getByRole('button', { name: /create inventory/i }));
    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledWith({ name: 'My inv' }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });
});

