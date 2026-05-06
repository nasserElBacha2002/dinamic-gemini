import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { AUTH_LOGOUT_PATH } from '../../constants/authApiPaths';
import { ROUTE_LOGIN } from '../../constants/appRoutes';
import { getCurrentUser } from './api';
import { getStoredSession, setStoredSession, clearStoredSession } from './storage';
import { AuthContext, AuthContextValue, createInitialAuthState } from './store';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider — Phase 4 implementation.
 *
 * Holds user + token; persists token in localStorage; bootstraps session on mount
 * via stored token + GET /auth/me. Login/logout persist or clear token.
 *
 * Bootstrap stays in a local effect (not TanStack Query) so this provider keeps a single source of truth
 * for token + user + initialized; moving GET /auth/me to Query would require revisiting that contract.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [state, setState] = useState(() => {
    const session = getStoredSession();
    const token = session?.accessToken ?? null;
    return token ? { ...createInitialAuthState(), token } : createInitialAuthState(true);
  });

  useEffect(() => {
    const bootstrapToken = state.token;

    if (!bootstrapToken) {
      let cleared = false;
      void Promise.resolve().then(() => {
        if (cleared) return;
        setState((prev) => (prev.initialized ? prev : { ...prev, initialized: true }));
      });
      return () => {
        cleared = true;
      };
    }

    let cancelled = false;

    // Fail-closed: any /auth/me failure (401, network, etc.) clears token and treats as unauthenticated.
    // We do not distinguish invalid/expired token from temporary backend failure; both result in logout.
    getCurrentUser(bootstrapToken)
      .then((user) => {
        if (cancelled) return;
        setState((prev) => {
          if (prev.token !== bootstrapToken) return prev;
          return { user, token: bootstrapToken, initialized: true };
        });
      })
      .catch(() => {
        if (cancelled) return;
        let invalidateSession = false;
        setState((prev) => {
          if (prev.token !== bootstrapToken) return prev;
          invalidateSession = true;
          return createInitialAuthState(true);
        });
        // Keep I/O out of the updater when possible; clear storage only when state transition logged out this bootstrap.
        if (invalidateSession) {
          clearStoredSession();
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.token]);

  const value: AuthContextValue = useMemo(
    () => ({
      ...state,
      login: (user, token) => {
        setStoredSession(token, null);
        setState({ user, token, initialized: true });
      },
      logout: () => {
        const session = getStoredSession();
        const accessToken = session?.accessToken ?? null;
        const refreshToken = session?.refreshToken ?? null;

        if (refreshToken) {
          const apiBase = import.meta.env.VITE_API_BASE_URL ?? '';
          const body = JSON.stringify({ refresh_token: refreshToken });
          const headers: HeadersInit = { 'Content-Type': 'application/json' };
          if (accessToken) {
            (headers as Record<string, string>)['Authorization'] = `Bearer ${accessToken}`;
          }
          // Fire-and-forget backend logout; always clear local session afterwards.
          fetch(`${apiBase}${AUTH_LOGOUT_PATH}`, {
            method: 'POST',
            headers,
            body,
          }).catch(() => {
            // Ignore network/logout errors; session will still be cleared locally.
          });
        }

        clearStoredSession();
        setState(createInitialAuthState(true));
        if (typeof window !== 'undefined') {
          window.location.assign(ROUTE_LOGIN);
        }
      },
    }),
    [state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
