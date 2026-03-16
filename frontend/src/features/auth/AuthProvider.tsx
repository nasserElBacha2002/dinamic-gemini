import type { ReactNode } from 'react';
import React, { useMemo, useState } from 'react';
import { AuthContext, AuthContextValue, createInitialAuthState } from './store';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider — Phase 1 implementation.
 *
 * Currently provides a minimal in-memory auth context with no persistence and
 * no integration with backend auth. Later phases will wire login/logout and
 * token handling.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [state, setState] = useState(createInitialAuthState);

  const value: AuthContextValue = useMemo(
    () => ({
      ...state,
      login: (user, token) => {
        // Phase 1: basic in-memory update; real login flow comes later.
        setState({ user, token });
      },
      logout: () => {
        setState(createInitialAuthState());
      },
    }),
    [state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

