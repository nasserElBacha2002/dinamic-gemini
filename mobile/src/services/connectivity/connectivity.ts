export interface ConnectivityState {
  readonly isOnline: boolean;
  readonly checkedAt: string;
}

export async function getConnectivityState(): Promise<ConnectivityState> {
  // Offline-first capture does not require network. Without a native NetInfo dependency in Fase 1,
  // report "unknown as online" and let API calls surface network failures.
  return { isOnline: true, checkedAt: new Date().toISOString() };
}

