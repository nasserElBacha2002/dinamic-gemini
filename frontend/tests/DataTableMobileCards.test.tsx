import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import DataTable from '../src/components/ui/DataTable';
import DataTableMobileCard from '../src/components/ui/DataTableMobileCard';
import * as breakpointHook from '../src/hooks/useAppBreakpoint';

vi.mock('../src/hooks/useAppBreakpoint', async () => {
  const actual = await vi.importActual<typeof import('../src/hooks/useAppBreakpoint')>(
    '../src/hooks/useAppBreakpoint'
  );
  return {
    ...actual,
    useAppBreakpoint: vi.fn(),
  };
});

const useAppBreakpointMock = vi.mocked(breakpointHook.useAppBreakpoint);

type Row = { id: string; name: string };

function renderTable(compact: boolean) {
  useAppBreakpointMock.mockReturnValue({
    isMdUp: !compact,
    isSmUp: true,
    isMobileNav: compact,
    isCompact: compact,
    isDesktopShell: !compact,
  });
  const theme = createTheme();
  const rows: Row[] = [
    { id: '1', name: 'Alpha' },
    { id: '2', name: 'Beta' },
  ];
  return render(
    <ThemeProvider theme={theme}>
      <DataTable
        testId="sample-table"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { id: 'name', label: 'Name', cell: (r) => r.name },
        ]}
        renderMobileItem={(r) => (
          <DataTableMobileCard ariaLabel={r.name}>
            <span>{r.name}</span>
          </DataTableMobileCard>
        )}
      />
    </ThemeProvider>
  );
}

describe('DataTable mobile cards', () => {
  it('renders table headers on desktop', () => {
    renderTable(false);
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('renders cards instead of table headers on compact viewport', () => {
    renderTable(true);
    expect(screen.queryByRole('columnheader', { name: 'Name' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Alpha')).toBeInTheDocument();
    expect(screen.getByLabelText('Beta')).toBeInTheDocument();
  });
});
