/**
 * Phase 9 — auth state fan-out for offline ops (login / restore / refresh / vault).
 */

export type AuthState = 'authenticated' | 'unauthenticated';

type Listener = (state: AuthState) => void;

const listeners = new Set<Listener>();

export function subscribeAuthState(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitAuthState(state: AuthState): void {
  for (const listener of listeners) {
    try {
      listener(state);
    } catch {
      // never break auth path
    }
  }
}
