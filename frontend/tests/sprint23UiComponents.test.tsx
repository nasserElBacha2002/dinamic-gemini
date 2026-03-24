/**
 * Sprint 2.3 — smoke tests for reusable UI base (theme + provider wiring).
 */

import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import {
  KpiCard,
  StatusBadge,
  EmptyState,
  ConfirmDialog,
  AppSnackbarProvider,
  useAppSnackbar,
} from '../src/components/ui';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('Sprint 2.3 UI base', () => {
  it('KpiCard renders label and value', () => {
    render(
      <WithTheme>
        <KpiCard label="Pending review" value={12} />
      </WithTheme>
    );
    expect(screen.getByText('Pending review')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('StatusBadge renders semantic chip', () => {
    render(
      <WithTheme>
        <StatusBadge label="Confirmed" semantic="success" />
      </WithTheme>
    );
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('EmptyState supports title and message', () => {
    render(
      <WithTheme>
        <EmptyState title="Nothing here" message="Add an item to continue." />
      </WithTheme>
    );
    expect(screen.getByRole('heading', { name: /nothing here/i })).toBeInTheDocument();
    expect(screen.getByText(/add an item/i)).toBeInTheDocument();
  });

  it('ConfirmDialog calls onConfirm', async () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <WithTheme>
        <ConfirmDialog
          open
          title="Delete?"
          description="This cannot be undone."
          onClose={onClose}
          onConfirm={onConfirm}
          confirmLabel="Delete"
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('useAppSnackbar shows message inside provider', () => {
    function Probe() {
      const { showSnackbar } = useAppSnackbar();
      return (
        <button type="button" onClick={() => showSnackbar('Saved', 'success')}>
          Go
        </button>
      );
    }
    render(
      <WithTheme>
        <AppSnackbarProvider>
          <Probe />
        </AppSnackbarProvider>
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /go/i }));
    expect(screen.getByText('Saved')).toBeInTheDocument();
  });
});
