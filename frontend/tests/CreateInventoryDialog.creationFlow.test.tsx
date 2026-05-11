import '@testing-library/jest-dom/vitest';
import React from 'react';
import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CreateInventoryDialog from '../src/components/CreateInventoryDialog';

const mockUseClients = vi.fn();
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

describe('CreateInventoryDialog (inventory creation flow)', () => {
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
  });

  it('creates inventory from the single-step dialog with required client', async () => {
    const { createInventoryFn, onSuccess } = renderDialog();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^cliente$/i }));
    fireEvent.click(screen.getByRole('option', { name: /cliente uno/i }));
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), {
      target: { value: 'My inv' },
    });
    fireEvent.click(screen.getByRole('button', { name: /crear inventario|create inventory action/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    expect(createInventoryFn).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'My inv',
        processing_mode: 'production',
        client_id: 'client-1',
      }),
    );
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('renders client selector with placeholder option only', () => {
    renderDialog();
    const selector = screen.getByRole('combobox', { name: /^cliente$/i });
    expect(selector).toBeInTheDocument();
    expect(screen.getByText(/seleccioná el cliente al que pertenece este inventario/i)).toBeInTheDocument();
    fireEvent.mouseDown(selector);
    expect(screen.getByRole('option', { name: /seleccioná un cliente/i })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /sin cliente/i })).not.toBeInTheDocument();
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

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^cliente$/i }));
    fireEvent.click(screen.getByRole('option', { name: /cliente dos/i }));
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), {
      target: { value: 'Lab inv' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^prueba$/i }));
    fireEvent.click(screen.getByRole('button', { name: /crear inventario|create inventory action/i }));

    await waitFor(() => expect(createInventoryFn).toHaveBeenCalledTimes(1));
    expect(createInventoryFn).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Lab inv', processing_mode: 'test', client_id: 'client-2' }),
    );
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('does not call create when no client is selected', async () => {
    const { createInventoryFn } = renderDialog();
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), {
      target: { value: 'No client' },
    });
    fireEvent.click(screen.getByRole('button', { name: /crear inventario|create inventory action/i }));
    await waitFor(() =>
      expect(
        screen.getByText(/seleccioná un cliente para crear el inventario|select a client to create the inventory/i),
      ).toBeInTheDocument(),
    );
    expect(createInventoryFn).not.toHaveBeenCalled();
  });

  it('does not offer a second wizard step for reference images', () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/nombre del inventario|inventory name/i), {
      target: { value: 'My inv' },
    });
    expect(screen.queryByRole('button', { name: /continue|continuar/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: /referencias visuales|reference step title/i }),
    ).not.toBeInTheDocument();
  });
});
