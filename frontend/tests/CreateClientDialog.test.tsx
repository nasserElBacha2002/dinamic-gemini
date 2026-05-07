import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CreateClientDialog from '../src/components/CreateClientDialog';

describe('CreateClientDialog', () => {
  it('validates empty name before submit', async () => {
    const createClientFn = vi.fn();
    render(
      <CreateClientDialog
        open
        onClose={() => {}}
        onSuccess={() => {}}
        createClientFn={createClientFn}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /crear/i }));
    expect(await screen.findByText(/nombre del cliente es obligatorio/i)).toBeInTheDocument();
    expect(createClientFn).not.toHaveBeenCalled();
  });

  it('submits valid name and closes on success', async () => {
    const createClientFn = vi.fn().mockResolvedValue({ id: 'client-1' });
    const onClose = vi.fn();
    const onSuccess = vi.fn();
    render(
      <CreateClientDialog
        open
        onClose={onClose}
        onSuccess={onSuccess}
        createClientFn={createClientFn}
      />
    );

    fireEvent.change(screen.getByLabelText(/nombre del cliente/i), { target: { value: 'Cliente Sur' } });
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(createClientFn).toHaveBeenCalledWith({ name: 'Cliente Sur' }));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
