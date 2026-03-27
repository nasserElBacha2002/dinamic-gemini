/**
 * Sprint 5.2 — shared confirm shell (loading label, callbacks).
 */

import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ConfirmDialog from '../src/components/ui/ConfirmDialog';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('ConfirmDialog', () => {
  it('calls onConfirm when confirm is clicked', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <WithTheme>
        <ConfirmDialog
          open
          title="Delete item?"
          description="This cannot be undone."
          onClose={onClose}
          onConfirm={onConfirm}
          confirmLabel="Delete"
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when cancel is clicked', () => {
    const onClose = vi.fn();
    render(
      <WithTheme>
        <ConfirmDialog
          open
          title="T"
          description="D"
          onClose={onClose}
          onConfirm={vi.fn()}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders inline error when errorMessage is set', () => {
    render(
      <WithTheme>
        <ConfirmDialog
          open
          title="T"
          description="D"
          onClose={vi.fn()}
          onConfirm={vi.fn()}
          errorMessage="Request failed — try again."
        />
      </WithTheme>
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/Request failed/i);
  });

  it('shows confirmPendingLabel and disables actions while loading', () => {
    render(
      <WithTheme>
        <ConfirmDialog
          open
          title="T"
          description="D"
          onClose={vi.fn()}
          onConfirm={vi.fn()}
          loading
          confirmLabel="Submit"
          confirmPendingLabel="Submitting…"
        />
      </WithTheme>
    );
    expect(screen.getByRole('button', { name: 'Submitting…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});
