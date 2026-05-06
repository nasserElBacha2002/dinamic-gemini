import React, { type ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../../src/theme';
import { ApiError } from '../../src/api/types';
import i18n from '../../src/i18n';
import ErrorAlert from '../../src/components/ui/ErrorAlert';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('ErrorAlert', () => {
  it('renders explicit message for backwards compatibility', () => {
    render(
      <WithTheme>
        <ErrorAlert message="Error controlado" />
      </WithTheme>
    );

    expect(screen.getByRole('alert').textContent ?? '').toContain('Error controlado');
  });

  it('normalizes known ApiError using visible translation', () => {
    const apiError = new ApiError('Not Found', 404, { code: 'INVENTORY_NOT_FOUND' });
    render(
      <WithTheme>
        <ErrorAlert error={apiError} context="inventory" />
      </WithTheme>
    );

    expect(screen.getByRole('alert').textContent ?? '').not.toContain('Not Found');
    expect(screen.getByText(i18n.t('errors.not_found'))).toBeInTheDocument();
  });

  it('does not expose raw technical message for unknown errors', () => {
    render(
      <WithTheme>
        <ErrorAlert error={new Error('technical stack trace message')} context="analytics" />
      </WithTheme>
    );

    expect(screen.getByRole('alert').textContent ?? '').not.toContain('technical stack trace message');
    expect(screen.getByText(i18n.t('errors.load_metrics'))).toBeInTheDocument();
  });

  it('keeps retry button behavior', () => {
    const onRetry = vi.fn();
    render(
      <WithTheme>
        <ErrorAlert message="Error controlado" onRetry={onRetry} />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('passes onClose to the underlying alert close action', () => {
    const onClose = vi.fn();
    render(
      <WithTheme>
        <ErrorAlert message="Closable error" onClose={onClose} />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: /close|cerrar/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

