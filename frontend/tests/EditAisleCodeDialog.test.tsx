import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import EditAisleCodeDialog from '../src/features/inventories/components/EditAisleCodeDialog';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('EditAisleCodeDialog', () => {
  const updateAisleFn = vi.fn();

  beforeEach(() => {
    updateAisleFn.mockReset();
    updateAisleFn.mockResolvedValue({ id: 'a1', code: 'B-02' });
  });

  it('opens with current code and disables save when unchanged', () => {
    render(
      <WithTheme>
        <EditAisleCodeDialog
          open
          currentCode="A-01"
          onClose={() => {}}
          updateAisleFn={updateAisleFn}
        />
      </WithTheme>,
    );

    expect(screen.getByTestId('edit-aisle-code-input')).toHaveValue('A-01');
    expect(screen.getByTestId('edit-aisle-code-save')).toBeDisabled();
  });

  it('rejects empty code', () => {
    render(
      <WithTheme>
        <EditAisleCodeDialog
          open
          currentCode="A-01"
          onClose={() => {}}
          updateAisleFn={updateAisleFn}
        />
      </WithTheme>,
    );

    fireEvent.change(screen.getByTestId('edit-aisle-code-input'), { target: { value: '  ' } });
    expect(screen.getByTestId('edit-aisle-code-save')).toBeDisabled();
    expect(updateAisleFn).not.toHaveBeenCalled();
  });

  it('pre-validates duplicate against existingCodes', async () => {
    render(
      <WithTheme>
        <EditAisleCodeDialog
          open
          currentCode="A-01"
          existingCodes={['B-02']}
          onClose={() => {}}
          updateAisleFn={updateAisleFn}
        />
      </WithTheme>,
    );

    fireEvent.change(screen.getByTestId('edit-aisle-code-input'), { target: { value: 'b-02' } });
    fireEvent.click(screen.getByTestId('edit-aisle-code-save'));

    expect(
      await screen.findByText(/ya existe un pasillo|validation duplicate|duplicad/i),
    ).toBeInTheDocument();
    expect(updateAisleFn).not.toHaveBeenCalled();
  });

  it('calls mutation on save when code changes', async () => {
    const onSuccess = vi.fn();
    render(
      <WithTheme>
        <EditAisleCodeDialog
          open
          currentCode="A-01"
          onClose={() => {}}
          onSuccess={onSuccess}
          updateAisleFn={updateAisleFn}
        />
      </WithTheme>,
    );

    fireEvent.change(screen.getByTestId('edit-aisle-code-input'), { target: { value: 'C-03' } });
    fireEvent.click(screen.getByTestId('edit-aisle-code-save'));

    await waitFor(() => expect(updateAisleFn).toHaveBeenCalledWith({ code: 'C-03' }));
    expect(onSuccess).toHaveBeenCalled();
  });
});
