/**
 * Shared BaseDialog shell — title id / aria, close button + disableClose.
 */

import '@testing-library/jest-dom/vitest';
import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button, ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import BaseDialog from '../src/components/ui/BaseDialog';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('BaseDialog', () => {
  it('renders title and wires aria-labelledby to the title element', () => {
    render(
      <WithTheme>
        <BaseDialog open title="Dialog title" onClose={() => {}}>
          Body
        </BaseDialog>
      </WithTheme>
    );
    const dialog = screen.getByRole('dialog');
    const labelledBy = dialog.getAttribute('aria-labelledby');
    expect(labelledBy).toBeTruthy();
    const titleEl = document.getElementById(labelledBy!);
    expect(titleEl).not.toBeNull();
    expect(titleEl).toHaveTextContent('Dialog title');
  });

  it('disables header close button when disableClose is true', () => {
    render(
      <WithTheme>
        <BaseDialog open title="T" onClose={vi.fn()} showCloseButton disableClose>
          Body
        </BaseDialog>
      </WithTheme>
    );
    expect(screen.getByRole('button', { name: /cerrar|close/i })).toBeDisabled();
  });

  it('calls onClose when header close is clicked and close is allowed', () => {
    const onClose = vi.fn();
    render(
      <WithTheme>
        <BaseDialog open title="T" onClose={onClose} showCloseButton>
          Body
        </BaseDialog>
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /cerrar|close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders custom actions', () => {
    render(
      <WithTheme>
        <BaseDialog
          open
          title="T"
          onClose={() => {}}
          actions={<Button>Action one</Button>}
        >
          Body
        </BaseDialog>
      </WithTheme>
    );
    expect(screen.getByRole('button', { name: 'Action one' })).toBeInTheDocument();
  });

  it('accepts object, function, and array actionsSx values', () => {
    const { rerender } = render(
      <WithTheme>
        <BaseDialog open title="T" onClose={() => {}} actions={<Button>Action one</Button>} actionsSx={{ gap: 1 }}>
          Body
        </BaseDialog>
      </WithTheme>
    );

    expect(screen.getByRole('button', { name: 'Action one' })).toBeInTheDocument();

    rerender(
      <WithTheme>
        <BaseDialog
          open
          title="T"
          onClose={() => {}}
          actions={<Button>Action one</Button>}
          actionsSx={(theme) => ({ color: theme.palette.primary.main })}
        >
          Body
        </BaseDialog>
      </WithTheme>
    );

    expect(screen.getByRole('button', { name: 'Action one' })).toBeInTheDocument();

    rerender(
      <WithTheme>
        <BaseDialog
          open
          title="T"
          onClose={() => {}}
          actions={<Button>Action one</Button>}
          actionsSx={[{ gap: 1 }, { justifyContent: 'flex-end' }]}
        >
          Body
        </BaseDialog>
      </WithTheme>
    );

    expect(screen.getByRole('button', { name: 'Action one' })).toBeInTheDocument();
  });
});
