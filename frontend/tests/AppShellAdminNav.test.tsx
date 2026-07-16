import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import AppShell from '../src/layout/AppShell';
import { AuthContext, createInitialAuthState } from '../src/features/auth/store';
import type { AuthContextValue } from '../src/features/auth/store';
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

function renderShell(username: string, desktop: boolean) {
  useAppBreakpointMock.mockReturnValue({
    isPhone: !desktop,
    isTablet: false,
    isDesktop: desktop,
    isMdUp: desktop,
    isSmUp: true,
    isMobileNav: !desktop,
    isCompact: !desktop,
    isDesktopShell: desktop,
    useTemporaryNavigation: !desktop,
    useMobileTableCards: !desktop,
    useFullscreenDialog: !desktop,
    useMobileFilterDrawer: !desktop,
    useVerticalWizard: !desktop,
  });

  const auth: AuthContextValue = {
    ...createInitialAuthState(true),
    user: { id: 'admin', username, role: 'administrator' },
    token: 't',
    login: vi.fn(),
    logout: vi.fn(),
  };
  const theme = createTheme();
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter initialEntries={['/']}>
        <AuthContext.Provider value={auth}>
          <AppShell />
        </AuthContext.Provider>
      </MemoryRouter>
    </ThemeProvider>
  );
}

describe('AppShell responsive navigation', () => {
  beforeEach(() => {
    useAppBreakpointMock.mockReset();
  });

  it('shows permanent nav links without hamburger on desktop', () => {
    renderShell('ops', true);
    expect(screen.queryByRole('button', { name: /abrir navegación|open navigation/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /clientes|clients/i })).toBeInTheDocument();
  });

  it('shows hamburger and opens temporary drawer on compact viewport', () => {
    renderShell('ops', false);
    const openBtn = screen.getByRole('button', { name: /abrir navegación|open navigation/i });
    expect(openBtn).toBeInTheDocument();
    fireEvent.click(openBtn);
    expect(screen.getByRole('link', { name: /clientes|clients/i })).toBeInTheDocument();
  });

  it('closes temporary nav after selecting a route', () => {
    renderShell('ops', false);
    fireEvent.click(screen.getByRole('button', { name: /abrir navegación|open navigation/i }));
    fireEvent.click(screen.getByRole('link', { name: /clientes|clients/i }));
    expect(screen.getByRole('button', { name: /abrir navegación|open navigation/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });
});

describe('AppShell admin AI nav', () => {
  beforeEach(() => {
    useAppBreakpointMock.mockReturnValue({
      isPhone: false,
      isTablet: false,
      isDesktop: true,
      isMdUp: true,
      isSmUp: true,
      isMobileNav: false,
      isCompact: false,
      isDesktopShell: true,
      useTemporaryNavigation: false,
      useMobileTableCards: false,
      useFullscreenDialog: false,
      useMobileFilterDrawer: false,
      useVerticalWizard: false,
    });
  });

  it('shows Clients nav entry', () => {
    renderShell('ops', true);
    expect(screen.getByRole('link', { name: /clientes|clients/i })).toHaveAttribute('href', '/clientes');
  });

  it('shows AI nav item when username is admin', () => {
    renderShell('admin', true);
    expect(screen.getByText(/Configuración de IA|AI configuration|IA y proveedores/i)).toBeInTheDocument();
  });

  it('hides AI nav item when username is not admin', () => {
    renderShell('ops', true);
    expect(screen.queryByText(/AI configuration|IA y proveedores/i)).not.toBeInTheDocument();
  });
});
