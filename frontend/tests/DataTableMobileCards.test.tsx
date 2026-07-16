import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Button } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import DataTable from '../src/components/ui/DataTable';
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

type Row = { id: string; name: string; state: string; hidden?: boolean };

function breakpoint(compact: boolean): breakpointHook.AppBreakpoint {
  return {
    isPhone: compact,
    isTablet: false,
    isDesktop: !compact,
    isMdUp: !compact,
    isSmUp: true,
    isMobileNav: compact,
    isCompact: compact,
    isDesktopShell: !compact,
    useTemporaryNavigation: compact,
    useMobileTableCards: compact,
    useFullscreenDialog: compact,
    useMobileFilterDrawer: compact,
    useVerticalWizard: compact,
  };
}

function renderTable(compact: boolean, onRowClick = vi.fn(), onPreview = vi.fn()) {
  useAppBreakpointMock.mockReturnValue(breakpoint(compact));
  const rows: Row[] = [
    { id: '1', name: 'Alpha', state: 'Ready' },
    { id: '2', name: 'Beta', state: 'Done', hidden: true },
  ];
  return {
    onRowClick,
    onPreview,
    ...render(
      <ThemeProvider theme={createTheme()}>
        <DataTable
          testId="sample-table"
          rows={rows}
          rowKey={(r) => r.id}
          columns={[{ id: 'name', label: 'Name', cell: (r) => r.name }]}
          onRowClick={onRowClick}
          mobile={{
            mode: 'card',
            title: (r) => r.name,
            subtitle: (r) => r.state,
            ariaLabel: (r) => `Open ${r.name}`,
            fields: [
              { id: 'state', label: 'State', value: (r) => r.state },
              { id: 'maybe', label: 'Maybe', value: () => 'Hidden', hidden: (r) => Boolean(r.hidden) },
            ],
            primaryAction: (r) => (
              <Button size="small" onClick={() => onPreview(r.id)}>
                Preview
              </Button>
            ),
          }}
        />
      </ThemeProvider>
    ),
  };
}

describe('DataTable mobile cards', () => {
  beforeEach(() => {
    useAppBreakpointMock.mockReset();
  });

  it('renders table headers on desktop', () => {
    renderTable(false);
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('renders declarative cards instead of table headers on compact viewport', () => {
    renderTable(true);
    expect(screen.queryByRole('columnheader', { name: 'Name' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Alpha' })).toBeInTheDocument();
    expect(screen.getAllByText('State')).toHaveLength(2);
    expect(screen.getAllByText('Ready')).toHaveLength(2);
    expect(screen.getByText('Hidden')).toBeInTheDocument();
  });

  it('reuses onRowClick for click and Enter on mobile cards', () => {
    const { onRowClick } = renderTable(true);
    fireEvent.click(screen.getByRole('link', { name: 'Open Alpha' }));
    fireEvent.keyDown(screen.getByRole('link', { name: 'Open Beta' }), { key: 'Enter' });
    expect(onRowClick).toHaveBeenCalledTimes(2);
    expect(onRowClick.mock.calls[0][0]).toMatchObject({ id: '1' });
    expect(onRowClick.mock.calls[1][0]).toMatchObject({ id: '2' });
  });

  it('does not open the row when an inner action is clicked', () => {
    const { onRowClick, onPreview } = renderTable(true);
    fireEvent.click(screen.getAllByRole('button', { name: 'Preview' })[0]);
    expect(onPreview).toHaveBeenCalledWith('1');
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('does not render nested buttons inside mobile cards', () => {
    const { container } = renderTable(true);
    expect(container.querySelector('button button')).toBeNull();
  });
});
