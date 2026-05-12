import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CreateClientSupplierDialog from '../src/components/CreateClientSupplierDialog';

describe('CreateClientSupplierDialog', () => {
  it('blocks submit when clientId is missing', async () => {
    const createClientSupplierFn = vi.fn();
    render(
      <CreateClientSupplierDialog
        open
        clientId=""
        onClose={() => {}}
        onSuccess={() => {}}
        createClientSupplierFn={createClientSupplierFn}
      />
    );

    fireEvent.change(screen.getByLabelText(/nombre del proveedor/i), {
      target: { value: 'Proveedor A' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    expect(await screen.findByText(/no se pudo determinar el cliente/i)).toBeInTheDocument();
    expect(createClientSupplierFn).not.toHaveBeenCalled();
  });

  it('submits valid supplier name scoped to client', async () => {
    const createClientSupplierFn = vi.fn().mockResolvedValue({ id: 'supplier-1' });
    const onClose = vi.fn();
    const onSuccess = vi.fn();
    render(
      <CreateClientSupplierDialog
        open
        clientId="client-123"
        onClose={onClose}
        onSuccess={onSuccess}
        createClientSupplierFn={createClientSupplierFn}
      />
    );

    fireEvent.change(screen.getByLabelText(/nombre del proveedor/i), {
      target: { value: 'Proveedor Norte' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(createClientSupplierFn).toHaveBeenCalledWith({ name: 'Proveedor Norte' }));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
