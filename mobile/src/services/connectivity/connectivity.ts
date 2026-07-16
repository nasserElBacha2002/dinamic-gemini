export type ConnectivityState = 'online' | 'offline' | 'unknown';

export type ConnectivityListener = (state: ConnectivityState) => void;

export interface ConnectivityService {
  getState(): ConnectivityState;
  subscribe(listener: ConnectivityListener): () => void;
  /** Test / manual override */
  setState?(state: ConnectivityState): void;
}

/**
 * Lightweight connectivity tracker.
 * Uses NetInfo when available; falls back to assuming online (tests / missing native module).
 */
export function createConnectivityService(): ConnectivityService {
  let state: ConnectivityState = 'unknown';
  const listeners = new Set<ConnectivityListener>();

  const emit = () => {
    for (const l of listeners) {
      l(state);
    }
  };

  try {
    // Optional peer — Expo projects may not have rebuilt native code yet.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const NetInfo = require('@react-native-community/netinfo') as {
      addEventListener: (cb: (s: { isConnected: boolean | null }) => void) => () => void;
      fetch: () => Promise<{ isConnected: boolean | null }>;
    };
    void NetInfo.fetch().then((s) => {
      state = s.isConnected === false ? 'offline' : s.isConnected === true ? 'online' : 'unknown';
      emit();
    });
    NetInfo.addEventListener((s) => {
      state = s.isConnected === false ? 'offline' : s.isConnected === true ? 'online' : 'unknown';
      emit();
    });
  } catch {
    state = 'online';
  }

  return {
    getState: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    setState: (next) => {
      state = next;
      emit();
    },
  };
}
