import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { Button, TextField } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import FilterToolbar from '../src/components/ui/FilterToolbar';
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

function breakpoint(mobile: boolean): breakpointHook.AppBreakpoint {
  return {
    isPhone: mobile,
    isTablet: false,
    isDesktop: !mobile,
    isMdUp: !mobile,
    isSmUp: true,
    isMobileNav: mobile,
    isCompact: mobile,
    isDesktopShell: !mobile,
    useTemporaryNavigation: mobile,
    useMobileTableCards: mobile,
    useFullscreenDialog: mobile,
    useMobileFilterDrawer: mobile,
    useVerticalWizard: mobile,
  };
}

function renderToolbar(mobile: boolean, onReset = vi.fn()) {
  useAppBreakpointMock.mockReturnValue(breakpoint(mobile));
  return {
    onReset,
    ...render(
      <ThemeProvider theme={createTheme()}>
        <FilterToolbar
          primary={<TextField label="Search" size="small" />}
          filters={<TextField label="Status" size="small" />}
          actions={<Button>Export</Button>}
          activeFilterCount={2}
          onReset={onReset}
        />
      </ThemeProvider>
    ),
  };
}

describe('FilterToolbar', () => {
  beforeEach(() => {
    useAppBreakpointMock.mockReset();
  });

  it('renders filters inline on desktop without duplication', () => {
    renderToolbar(false);
    expect(screen.getByLabelText('Search')).toBeInTheDocument();
    expect(screen.getByLabelText('Status')).toBeInTheDocument();
    expect(screen.getAllByLabelText('Status')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('keeps search visible and moves filters into drawer on mobile', () => {
    renderToolbar(true);
    expect(screen.getByLabelText('Search')).toBeInTheDocument();
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^filters \(2\)$|^filtros \(2\)$/i }));
    expect(screen.getByLabelText('Status')).toBeInTheDocument();
  });

  it('resets filters from mobile drawer and closes with Escape', () => {
    const { onReset } = renderToolbar(true);
    fireEvent.click(screen.getByRole('button', { name: /^filters \(2\)$|^filtros \(2\)$/i }));
    const drawer = screen.getByRole('presentation');
    fireEvent.click(within(drawer).getByRole('button', { name: /reset|restablecer|limpiar/i }));
    expect(onReset).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
  });
});
