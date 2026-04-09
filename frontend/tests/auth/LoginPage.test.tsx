/**
 * v3.2.1 Phase 4 — LoginPage tests.
 * Form render, submit triggers login, loading state, error display.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../../src/features/auth';
import LoginPage from '../../src/features/auth/LoginPage';
import { getStoredToken } from '../../src/features/auth/storage';

const mockLogin = vi.fn();
vi.mock('../../src/features/auth/api', () => ({
  login: (payload: { username: string; password: string }) => mockLogin(payload),
  getCurrentUser: vi.fn().mockRejectedValue(new Error('unauthorized')),
  getAuthErrorMessage: (err: unknown) => (err instanceof Error ? err.message : 'Authentication failed'),
}));

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Inventories home</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders login form with username, password and submit button', () => {
    renderLoginPage();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument();
    expect(screen.getByText('Admin login')).toBeInTheDocument();
  });

  it('disables submit when username or password is blank', () => {
    renderLoginPage();
    const submitBtn = screen.getByRole('button', { name: /log in/i });
    expect(submitBtn).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'a' } });
    expect(submitBtn).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'b' } });
    expect(submitBtn).toBeEnabled();
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: '   ' } });
    expect(submitBtn).toBeDisabled();
  });

  it('submit sends credentials to login API and shows loading state', async () => {
    mockLogin.mockImplementation(() => new Promise(() => {})); // never resolves
    renderLoginPage();

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: /log in/i }));

    expect(mockLogin).toHaveBeenCalledWith({ username: 'admin', password: 'secret' });
    expect(screen.getByRole('button', { name: /signing in/i })).toBeInTheDocument();
  });

  it('on login success stores token and navigates to dashboard', async () => {
    mockLogin.mockResolvedValue({
      access_token: 'jwt-123',
      token_type: 'bearer',
      expires_in: 300,
      user: { id: 'admin', username: 'admin', role: 'administrator' },
    });
    renderLoginPage();

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /log in/i }));

    expect(await screen.findByText('Inventories home')).toBeInTheDocument();
    // v3.2.3.E6: token is stored as a structured session; use helper for contract stability.
    expect(getStoredToken()).toBe('jwt-123');
  });

  it('on login failure shows error message', async () => {
    mockLogin.mockRejectedValue(new Error('Invalid credentials.'));
    renderLoginPage();

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: /log in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Invalid credentials/i);
    expect(localStorage.getItem('dinamic_auth_token')).toBeNull();
  });
});
