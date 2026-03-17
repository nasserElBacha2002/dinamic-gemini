import type { ReactNode } from 'react';
import React, { useEffect, useMemo, useState } from 'react';
import { getCurrentUser } from './api';
import { getStoredToken, setStoredToken, clearStoredToken } from './storage';
import { AuthContext, AuthContextValue, createInitialAuthState } from './store';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider — Phase 4 implementation.
 *
 * Holds user + token; persists token in localStorage; bootstraps session on mount
 * via stored token + GET /auth/me. Login/logout persist or clear token.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [state, setState] = useState(() => createInitialAuthState());

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setState((s) => ({ ...s, initialized: true }));
      return;
    }
    // Fail-closed: any /auth/me failure (401, network, etc.) clears token and treats as unauthenticated.
    // We do not distinguish invalid/expired token from temporary backend failure; both result in logout.
    getCurrentUser(token)
      .then((user) => {
        setState({ user, token, initialized: true });
      })
      .catch(() => {
        clearStoredToken();
        setState(createInitialAuthState(true));
      });
  }, []);

  const value: AuthContextValue = useMemo(
    () => ({
      ...state,
      login: (user, token) => {
        setStoredToken(token);
        setState({ user, token, initialized: true });
      },
      logout: () => {
        clearStoredToken();
        setState(createInitialAuthState(true));
      },
    }),
    [state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
