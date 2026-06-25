import type { ReactNode } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import TableSection from '../src/components/ui/TableSection';
import type { DataTableColumn } from '../src/components/ui/DataTable';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

type Row = { id: string; name: string };

const columns: DataTableColumn<Row>[] = [
  { id: 'name', label: 'Name', sortable: true, cell: (r) => r.name },
];

describe('TableSection', () => {
  it('renders title, toolbar, and table rows', () => {
    render(
      <WithTheme>
        <TableSection<Row>
          title="Inventories"
          description="Manage inventory operations"
          toolbar={<div data-testid="toolbar-slot">Toolbar</div>}
          table={{
            rows: [{ id: '1', name: 'Alpha' }],
            rowKey: (r) => r.id,
            columns,
          }}
        />
      </WithTheme>
    );
    expect(screen.getByRole('heading', { name: /inventories/i })).toBeInTheDocument();
    expect(screen.getByText(/manage inventory operations/i)).toBeInTheDocument();
    expect(screen.getByTestId('toolbar-slot')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('renders only error alert when hideSectionOnError is set', () => {
    render(
      <WithTheme>
        <TableSection<Row>
          title="Hidden on error"
          error={{ message: 'Load failed' }}
          hideSectionOnError
          table={{
            rows: [{ id: '1', name: 'Alpha' }],
            rowKey: (r) => r.id,
            columns,
          }}
        />
      </WithTheme>
    );
    expect(screen.getByText('Load failed')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /hidden on error/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
  });

  it('renders header and footer slots', () => {
    render(
      <WithTheme>
        <TableSection<Row>
          title="With slots"
          headerSlot={<div data-testid="header-slot">Header</div>}
          footerSlot={<div data-testid="footer-slot">Footer</div>}
          table={{
            rows: [],
            rowKey: (r) => r.id,
            columns,
            emptyState: { message: 'No rows' },
          }}
        />
      </WithTheme>
    );
    expect(screen.getByTestId('header-slot')).toBeInTheDocument();
    expect(screen.getByTestId('footer-slot')).toBeInTheDocument();
    expect(screen.getByText('No rows')).toBeInTheDocument();
  });

  it('hides table when hideTableOnError and error are set', () => {
    render(
      <WithTheme>
        <TableSection<Row>
          title="Partial error"
          error={{ message: 'Partial failure' }}
          hideTableOnError
          table={{
            rows: [{ id: '1', name: 'Alpha' }],
            rowKey: (r) => r.id,
            columns,
          }}
        />
      </WithTheme>
    );
    expect(screen.getByText('Partial failure')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /partial error/i })).toBeInTheDocument();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
  });
});
