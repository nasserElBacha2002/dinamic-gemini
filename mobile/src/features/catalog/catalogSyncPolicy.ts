/** Minimum interval between automatic background catalog sync attempts. */
export const CATALOG_AUTO_SYNC_MIN_INTERVAL_MS = 60_000;

export type ConnectivityState = 'online' | 'offline' | 'unknown';

export function shouldTriggerReconnectCatalogSync(
  authenticated: boolean,
  previousState: ConnectivityState,
  nextState: ConnectivityState,
): boolean {
  return authenticated && previousState === 'offline' && nextState === 'online';
}

export type CatalogSyncTrigger =
  | 'bootstrap'
  | 'reconnect'
  | 'manual'
  | 'foreground'
  | 'screen_refresh'
  | 'login';

export type CatalogSyncStatus =
  | 'SUCCESS'
  | 'PARTIAL'
  | 'FAILED'
  | 'NO_CHANGES'
  | 'SKIPPED_OFFLINE'
  | 'SKIPPED_THROTTLE';

export function shouldBypassSyncThrottle(
  trigger: CatalogSyncTrigger,
  force?: boolean,
): boolean {
  if (force) {
    return true;
  }
  return trigger === 'manual' || trigger === 'reconnect' || trigger === 'login';
}

export function isAutoSyncThrottled(
  lastSuccessfulSyncAtMs: number | null,
  nowMs: number,
): boolean {
  if (lastSuccessfulSyncAtMs === null) {
    return false;
  }
  return nowMs - lastSuccessfulSyncAtMs < CATALOG_AUTO_SYNC_MIN_INTERVAL_MS;
}
