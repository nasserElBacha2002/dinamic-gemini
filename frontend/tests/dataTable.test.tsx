/**
 * Sprint 2.4 — DataTable shell (sort callbacks, empty state, no client-side data mutation).
 */

import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import DataTable, { type DataTableColumn } from '../src/components/ui/DataTable';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

type Row = { id: string; name: string };

describe('DataTable', () => {
  const columns: DataTableColumn<Row>[] = [
    { id: 'name', label: 'Name', sortable: true, cell: (r) => r.name },
  ];

  it('renders rows', () => {
    render(
      <WithTheme>
        <DataTable<Row>
          rows={[{ id: '1', name: 'Alpha' }]}
          rowKey={(r) => r.id}
          columns={columns}
        />
      </WithTheme>
    );
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('calls onSortChange when sortable header clicked', () => {
    const onSortChange = vi.fn();
    render(
      <WithTheme>
        <DataTable<Row>
          rows={[{ id: '1', name: 'Alpha' }]}
          rowKey={(r) => r.id}
          columns={columns}
          sort={{ sortBy: 'name', sortDir: 'asc', onSortChange }}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /name/i }));
    expect(onSortChange).toHaveBeenCalledWith('name', 'desc');
  });

  it('shows empty state when rows empty and emptyState provided', () => {
    render(
      <WithTheme>
        <DataTable<Row>
          rows={[]}
          rowKey={(r) => r.id}
          columns={columns}
          emptyState={{ title: 'Nothing here', message: 'Add a row to continue.' }}
        />
      </WithTheme>
    );
    expect(screen.getByRole('heading', { name: /nothing here/i })).toBeInTheDocument();
    expect(screen.getByText(/add a row/i)).toBeInTheDocument();
  });

  it('shows skeleton rows when loading', () => {
    const { container } = render(
      <WithTheme>
        <DataTable<Row>
          rows={[]}
          rowKey={(r) => r.id}
          columns={columns}
          loading
          skeletonRows={3}
        />
      </WithTheme>
    );
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });
});
