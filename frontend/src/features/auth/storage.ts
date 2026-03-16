/**
 * v3.2.1 Phase 4 — client-side token persistence.
 * Single key in localStorage; cleared on logout, read on bootstrap.
 */

const AUTH_TOKEN_KEY = 'dinamic_auth_token';

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string): void {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // Ignore quota or privacy errors
  }
}

export function clearStoredToken(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // Ignore
  }
}
