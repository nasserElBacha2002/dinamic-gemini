import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import RequireUsernameAdmin from '../src/features/auth/RequireUsernameAdmin';
import { AuthContext, createInitialAuthState } from '../src/features/auth/store';
import type { AuthContextValue } from '../src/features/auth/store';

function renderGate(username: string) {
  const auth: AuthContextValue = {
    ...createInitialAuthState(true),
    user: { id: 'admin', username, role: 'administrator' },
    token: 't',
    login: vi.fn(),
    logout: vi.fn(),
  };
  return render(
    <MemoryRouter initialEntries={['/admin/ai-config']}>
      <AuthContext.Provider value={auth}>
        <Routes>
          <Route
            path="/admin/ai-config"
            element={
              <RequireUsernameAdmin>
                <div data-testid="secret">inside</div>
              </RequireUsernameAdmin>
            }
          />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe('RequireUsernameAdmin', () => {
  it('renders children for admin username', () => {
    renderGate('admin');
    expect(screen.getByTestId('secret')).toBeInTheDocument();
  });

  it('blocks non-admin username with message', () => {
    renderGate('other');
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument();
    expect(screen.getByText(/Access denied|Acceso denegado/i)).toBeInTheDocument();
  });
});
