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

    fireEvent.click(screen.getByRole('button', { name: /create aisle/i }));
    expect(await screen.findByText(/aisle code is required/i)).toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText(/aisle code/i), { target: { value: ' a-01 ' } });
    fireEvent.click(screen.getByRole('button', { name: /create aisle/i }));
    expect(await screen.findByText(/already exists in this inventory/i)).toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText(/aisle code/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /create aisle/i }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(screen.getByRole('alert')).toHaveTextContent(/aisle\s+a1\s+created/i);
    expect(screen.getByRole('button', { name: /create another/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /create another/i }));
    expect(screen.queryByText(/created/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/aisle code/i)).toHaveValue('');
    expect(screen.getByLabelText(/aisle code/i)).toHaveFocus();
  });
});

