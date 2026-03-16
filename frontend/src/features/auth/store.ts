import { createContext, useContext } from 'react';
import type { AuthUser } from './types';

// Auth state and context — Phase 4: persistence, bootstrap, login/logout.

export interface AuthState {
  user: AuthUser | null;
  token: string | null;
  /** False until bootstrap (token check + optional /auth/me) has run. */
  initialized: boolean;
}

export interface AuthContextValue extends AuthState {
  login: (user: AuthUser, token: string) => void;
  logout: () => void;
}

const defaultState: AuthState = {
  user: null,
  token: null,
  initialized: false,
};

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider.');
  }
  return ctx;
}

export function createInitialAuthState(initialized = false): AuthState {
  return {
    user: null,
    token: null,
    initialized,
  };
}

