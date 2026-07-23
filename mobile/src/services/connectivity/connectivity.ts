export type ConnectivityState = 'online' | 'offline' | 'unknown';

export type ConnectivityListener = (state: ConnectivityState) => void;

export interface ConnectivitySnapshot {
  readonly state: ConnectivityState;
  readonly isConnected: boolean | null;
  readonly isInternetReachable: boolean | null;
  /** Raw NetInfo type string when available (wifi/cellular/ethernet/…); never SSID/IP. */
  readonly connectionType: string | null;
  readonly isCellular: boolean;
}

export interface ConnectivityService {
  getState(): ConnectivityState;
  /** True when the active path is cellular (not Wi‑Fi / ethernet). */
  isCellular?(): boolean;
  /** Best-effort network snapshot for observability (no PII). */
  getSnapshot?(): ConnectivitySnapshot;
  subscribe(listener: ConnectivityListener): () => void;
  /** Test / manual override */
  setState?(state: ConnectivityState): void;
  setCellular?(cellular: boolean): void;
  setConnectionType?(type: string | null): void;
}

/**
 * Lightweight connectivity tracker.
 * Uses NetInfo when available; falls back to assuming online (tests / missing native module).
 */
export function createConnectivityService(): ConnectivityService {
  let state: ConnectivityState = 'unknown';
  let cellular = false;
  let connectionType: string | null = null;
  let isConnected: boolean | null = null;
  let isInternetReachable: boolean | null = null;
  const listeners = new Set<ConnectivityListener>();

  const emit = () => {
    for (const l of listeners) {
      l(state);
    }
  };

  const applyNetInfo = (s: {
    isConnected: boolean | null;
    isInternetReachable?: boolean | null;
    type?: string | null;
  }) => {
    isConnected = s.isConnected;
    isInternetReachable =
      typeof s.isInternetReachable === 'boolean' || s.isInternetReachable === null
        ? s.isInternetReachable ?? null
        : null;
    state = s.isConnected === false ? 'offline' : s.isConnected === true ? 'online' : 'unknown';
    connectionType = typeof s.type === 'string' ? s.type : null;
    cellular = s.type === 'cellular';
    emit();
  };

  try {
    // Optional peer — Expo projects may not have rebuilt native code yet.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const NetInfo = require('@react-native-community/netinfo') as {
      addEventListener: (
        cb: (s: {
          isConnected: boolean | null;
          isInternetReachable?: boolean | null;
          type?: string | null;
        }) => void,
      ) => () => void;
      fetch: () => Promise<{
        isConnected: boolean | null;
        isInternetReachable?: boolean | null;
        type?: string | null;
      }>;
    };
    void NetInfo.fetch().then(applyNetInfo);
    NetInfo.addEventListener(applyNetInfo);
  } catch {
    state = 'online';
    isConnected = true;
  }

  return {
    getState: () => state,
    isCellular: () => cellular,
    getSnapshot: () => ({
      state,
      isConnected,
      isInternetReachable,
      connectionType,
      isCellular: cellular,
    }),
    subscribe: (listener) => {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    setState: (next) => {
      state = next;
      isConnected = next === 'offline' ? false : next === 'online' ? true : null;
      emit();
    },
    setCellular: (next) => {
      cellular = next;
      if (next) {
        connectionType = 'cellular';
      }
      emit();
    },
    setConnectionType: (type) => {
      connectionType = type;
      cellular = type === 'cellular';
      emit();
    },
  };
}
