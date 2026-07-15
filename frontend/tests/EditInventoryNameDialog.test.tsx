import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import EditInventoryNameDialog from '../src/features/inventories/components/EditInventoryNameDialog';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('EditInventoryNameDialog', () => {
  const updateInventoryFn = vi.fn();

  beforeEach(() => {
    updateInventoryFn.mockReset();
    updateInventoryFn.mockResolvedValue({ id: 'inv-1', name: 'Nuevo' });
  });

  it('opens with current name and disables save when unchanged', () => {
    render(
      <WithTheme>
        <EditInventoryNameDialog
          open
          currentName="Inventario A"
          onClose={() => {}}
          updateInventoryFn={updateInventoryFn}
        />
      </WithTheme>,
    );

    expect(screen.getByTestId('edit-inventory-name-input')).toHaveValue('Inventario A');
    expect(screen.getByTestId('edit-inventory-name-save')).toBeDisabled();
  });

  it('rejects empty name on save', async () => {
    render(
      <WithTheme>
        <EditInventoryNameDialog
          open
          currentName="Inventario A"
          onClose={() => {}}
          updateInventoryFn={updateInventoryFn}
        />
      </WithTheme>,
    );

    fireEvent.change(screen.getByTestId('edit-inventory-name-input'), { target: { value: '   ' } });
    // Save stays disabled when empty
    expect(screen.getByTestId('edit-inventory-name-save')).toBeDisabled();
    expect(updateInventoryFn).not.toHaveBeenCalled();
  });

  it('calls mutation on save when name changes', async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(
      <WithTheme>
        <EditInventoryNameDialog
          open
          currentName="Inventario A"
          onClose={onClose}
          onSuccess={onSuccess}
          updateInventoryFn={updateInventoryFn}
        />
      </WithTheme>,
    );

    fireEvent.change(screen.getByTestId('edit-inventory-name-input'), {
      target: { value: 'Inventario B' },
    });
    fireEvent.click(screen.getByTestId('edit-inventory-name-save'));

    await waitFor(() => expect(updateInventoryFn).toHaveBeenCalledWith({ name: 'Inventario B' }));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
