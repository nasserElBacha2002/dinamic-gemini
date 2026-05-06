import React from 'react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import CreateAisleDialog from '../src/components/CreateAisleDialog';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('CreateAisleDialog', () => {
  it('validates required aisle code inline', async () => {
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={async () => ({})}
        />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(
      await screen.findByText(/ingresá el código del pasillo|validation code required|código obligatorio/i)
    ).toBeInTheDocument();
  });

  it('pre-validates duplicate code when existing codes are provided', async () => {
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          existingAisleCodes={['A-01']}
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={async () => ({})}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: ' a-01 ' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(
      await screen.findByText(/ya existe un pasillo|validation duplicate|ya existe|duplicad/i)
    ).toBeInTheDocument();
  });

  it('shows success state with create another and close actions', async () => {
    const createAisleFn = vi.fn(async () => ({ id: 'a1' }));
    const onSuccess = vi.fn();
    const onClose = vi.fn();

    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          onClose={onClose}
          onSuccess={onSuccess}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(screen.getByRole('alert')).toHaveTextContent(/success created|creado|A1/i);
    expect(screen.getByRole('button', { name: /create another|crear otro/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cerrar|close/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /create another|crear otro/i }));
    expect(screen.queryByText(/created|creado/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/código|code label/i)).toHaveValue('');
    expect(screen.getByLabelText(/código|code label/i)).toHaveFocus();
  });
});

