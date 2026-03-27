/**
 * Sprint 2.4 — DataTable shell (sort callbacks, empty state, no client-side data mutation).
 */

import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import DataTable, { type DataTableColumn } from '../src/components/ui/DataTable';
import { DATATABLE_DEFAULT_EMPTY_MESSAGE } from '../src/constants/dataTable';

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

  it('shows default empty message when rows empty and emptyState omitted', () => {
    render(
      <WithTheme>
        <DataTable<Row> rows={[]} rowKey={(r) => r.id} columns={columns} />
      </WithTheme>
    );
    expect(screen.getByText(DATATABLE_DEFAULT_EMPTY_MESSAGE)).toBeInTheDocument();
  });

  it('calls onPageChange with next 1-based page when pagination next is used', () => {
    const onPageChange = vi.fn();
    const rows: Row[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i),
      name: `Row ${i}`,
    }));
    render(
      <WithTheme>
        <DataTable<Row>
          rows={rows}
          rowKey={(r) => r.id}
          columns={columns}
          pagination={{
            page: 1,
            pageSize: 10,
            totalItems: 35,
            onPageChange,
            onPageSizeChange: vi.fn(),
          }}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /go to next page/i }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('calls onRowClick with the row when a data row is clicked', () => {
    const onRowClick = vi.fn();
    render(
      <WithTheme>
        <DataTable<Row>
          rows={[{ id: '1', name: 'Alpha' }]}
          rowKey={(r) => r.id}
          columns={columns}
          onRowClick={onRowClick}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByText('Alpha'));
    expect(onRowClick).toHaveBeenCalledWith({ id: '1', name: 'Alpha' });
  });

  it('calls onPageSizeChange and resets to page 1 when rows per page changes', () => {
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();
    const rows: Row[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i),
      name: `Row ${i}`,
    }));
    render(
      <WithTheme>
        <DataTable<Row>
          rows={rows}
          rowKey={(r) => r.id}
          columns={columns}
          pagination={{
            page: 3,
            pageSize: 10,
            totalItems: 100,
            onPageChange,
            onPageSizeChange,
          }}
        />
      </WithTheme>
    );
    const select = screen.getByRole('combobox', { name: /^rows$/i });
    fireEvent.mouseDown(select);
    const opt25 = screen.getByRole('option', { name: '25' });
    fireEvent.click(opt25);
    expect(onPageSizeChange).toHaveBeenCalledWith(25);
    expect(onPageChange).toHaveBeenCalledWith(1);
  });
});
