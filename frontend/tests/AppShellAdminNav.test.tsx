import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AppShell from '../src/layout/AppShell';
import { AuthContext, createInitialAuthState } from '../src/features/auth/store';
import type { AuthContextValue } from '../src/features/auth/store';

function renderShell(username: string | null) {
  const auth: AuthContextValue = {
    ...createInitialAuthState(true),
    user: username
      ? { id: 'admin', username, role: 'administrator' }
      : null,
    token: username ? 't' : null,
    login: vi.fn(),
    logout: vi.fn(),
  };
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthContext.Provider value={auth}>
        <AppShell />
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe('AppShell admin AI nav', () => {
  it('shows AI nav item when username is admin', () => {
    renderShell('admin');
    expect(screen.getByText(/AI configuration|IA y proveedores/i)).toBeInTheDocument();
  });

  it('hides AI nav item when username is not admin', () => {
    renderShell('ops');
    expect(screen.queryByText(/AI configuration|IA y proveedores/i)).not.toBeInTheDocument();
  });
});
