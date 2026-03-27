/**
 * Row actions must not trigger DataTable row navigation (Inventory detail aisles table).
 */

import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import DataTable, { type DataTableColumn } from '../src/components/ui/DataTable';
import RowActionMenu from '../src/components/ui/RowActionMenu';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

type AisleRow = { id: string; code: string };

describe('DataTable + RowActionMenu', () => {
  it('invokes row action and does not call onRowClick when choosing a menu item', async () => {
    const onRowClick = vi.fn();
    const onUpload = vi.fn();

    const columns: DataTableColumn<AisleRow>[] = [
      { id: 'code', label: 'Code', cell: (r) => r.code },
      {
        id: 'actions',
        label: 'Actions',
        align: 'right',
        cell: () => (
          <RowActionMenu
            ariaLabel="Row actions"
            items={[
              { id: 'upload', label: 'Upload assets', onClick: onUpload },
              { id: 'process', label: 'Process aisle', onClick: vi.fn() },
            ]}
          />
        ),
      },
    ];

    render(
      <WithTheme>
        <DataTable<AisleRow>
          rows={[{ id: 'aisle-1', code: 'A-01' }]}
          rowKey={(r) => r.id}
          columns={columns}
          onRowClick={onRowClick}
        />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: /row actions/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /upload assets/i }));

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('still calls onRowClick when clicking a non-interactive cell', () => {
    const onRowClick = vi.fn();
    const columns: DataTableColumn<AisleRow>[] = [
      { id: 'code', label: 'Code', cell: (r) => r.code },
      {
        id: 'actions',
        label: 'Actions',
        align: 'right',
        cell: () => <RowActionMenu ariaLabel="Row actions" items={[{ id: 'x', label: 'X', onClick: vi.fn() }]} />,
      },
    ];

    render(
      <WithTheme>
        <DataTable<AisleRow>
          rows={[{ id: 'aisle-1', code: 'A-01' }]}
          rowKey={(r) => r.id}
          columns={columns}
          onRowClick={onRowClick}
        />
      </WithTheme>
    );

    fireEvent.click(screen.getByText('A-01'));
    expect(onRowClick).toHaveBeenCalledWith({ id: 'aisle-1', code: 'A-01' });
  });
});
