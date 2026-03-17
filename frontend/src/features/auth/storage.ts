/**
 * v3.2.3.E6 — client-side auth session persistence.
 *
 * Store both accessToken and refreshToken in a single localStorage entry so
 * the frontend can later implement refresh-token flows. Legacy helpers
 * (getStoredToken/setStoredToken/clearStoredToken) remain for backward
 * compatibility and delegate to the session-based storage.
 */

const AUTH_SESSION_KEY = 'dinamic_auth_session';
const LEGACY_AUTH_TOKEN_KEY = 'dinamic_auth_token';

export interface StoredSession {
  accessToken: string;
  refreshToken: string | null;
}

export function getStoredSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(AUTH_SESSION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredSession>;
      if (parsed && typeof parsed.accessToken === 'string') {
        return {
          accessToken: parsed.accessToken,
          refreshToken: parsed.refreshToken ?? null,
        };
      }
    }
    // Backward-compatibility: if only the legacy token key exists, expose it as a session with no refreshToken.
    const legacy = localStorage.getItem(LEGACY_AUTH_TOKEN_KEY);
    if (legacy && legacy.trim() !== '') {
      return { accessToken: legacy, refreshToken: null };
    }
  } catch {
    // Ignore parse or access errors.
  }
  return null;
}

export function setStoredSession(accessToken: string, refreshToken: string | null): void {
  try {
    const value: StoredSession = { accessToken, refreshToken };
    localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(value));
    // Clean up legacy key once we have a structured session stored.
    localStorage.removeItem(LEGACY_AUTH_TOKEN_KEY);
  } catch {
    // Ignore quota or privacy errors
  }
}

export function clearStoredSession(): void {
  try {
    localStorage.removeItem(AUTH_SESSION_KEY);
    localStorage.removeItem(LEGACY_AUTH_TOKEN_KEY);
  } catch {
    // Ignore
  }
}

// --- Legacy helpers used by existing code paths ---

export function getStoredToken(): string | null {
  const session = getStoredSession();
  return session?.accessToken ?? null;
}

export function setStoredToken(token: string): void {
  // When only an access token is known, persist it as a session with no refreshToken.
  setStoredSession(token, null);
}

export function clearStoredToken(): void {
  clearStoredSession();
}
