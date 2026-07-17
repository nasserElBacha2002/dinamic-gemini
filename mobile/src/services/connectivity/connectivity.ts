export type ConnectivityState = 'online' | 'offline' | 'unknown';

export type ConnectivityListener = (state: ConnectivityState) => void;

export interface ConnectivityService {
  getState(): ConnectivityState;
  /** True when the active path is cellular (not Wi‑Fi / ethernet). */
  isCellular?(): boolean;
  subscribe(listener: ConnectivityListener): () => void;
  /** Test / manual override */
  setState?(state: ConnectivityState): void;
  setCellular?(cellular: boolean): void;
}

/**
 * Lightweight connectivity tracker.
 * Uses NetInfo when available; falls back to assuming online (tests / missing native module).
 */
export function createConnectivityService(): ConnectivityService {
  let state: ConnectivityState = 'unknown';
  let cellular = false;
  const listeners = new Set<ConnectivityListener>();

  const emit = () => {
    for (const l of listeners) {
      l(state);
    }
  };

  const applyNetInfo = (s: {
    isConnected: boolean | null;
    type?: string | null;
  }) => {
    state = s.isConnected === false ? 'offline' : s.isConnected === true ? 'online' : 'unknown';
    cellular = s.type === 'cellular';
    emit();
  };

  try {
    // Optional peer — Expo projects may not have rebuilt native code yet.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const NetInfo = require('@react-native-community/netinfo') as {
      addEventListener: (
        cb: (s: { isConnected: boolean | null; type?: string | null }) => void,
      ) => () => void;
      fetch: () => Promise<{ isConnected: boolean | null; type?: string | null }>;
    };
    void NetInfo.fetch().then(applyNetInfo);
    NetInfo.addEventListener(applyNetInfo);
  } catch {
    state = 'online';
  }

  return {
    getState: () => state,
    isCellular: () => cellular,
    subscribe: (listener) => {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    setState: (next) => {
      state = next;
      emit();
    },
    setCellular: (next) => {
      cellular = next;
      emit();
    },
  };
}