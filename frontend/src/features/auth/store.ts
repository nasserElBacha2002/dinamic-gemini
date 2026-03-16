import { createContext, useContext } from 'react';
import type { AuthUser } from './types';

// Auth state and context — Phase 1 defines boundaries only.

export interface AuthState {
  user: AuthUser | null;
  token: string | null;
}

export interface AuthContextValue extends AuthState {
  login: (user: AuthUser, token: string) => void;
  logout: () => void;
}

const defaultState: AuthState = {
  user: null,
  token: null,
};

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider (to be wired in later phases).');
  }
  return ctx;
}

export function createInitialAuthState(): AuthState {
  // Phase 1: no persistence yet; later phases will hydrate from storage or /auth/me.
  return defaultState;
}

