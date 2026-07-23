import type { NormalizedNetworkType } from './types';

/**
 * Normalize NetInfo / connectivity types to the Phase 0 catalog.
 * Never includes SSID, operator, IP, or MAC.
 */
export function normalizeNetworkType(input: {
  readonly isConnected?: boolean | null;
  readonly type?: string | null;
  readonly isCellular?: boolean;
}): NormalizedNetworkType {
  if (input.isConnected === false) {
    return 'offline';
  }
  const raw = (input.type || '').toLowerCase().trim();
  if (raw === 'wifi' || raw === 'wi-fi') {
    return 'wifi';
  }
  if (raw === 'cellular' || raw === 'cell' || input.isCellular === true) {
    return 'cellular';
  }
  if (raw === 'ethernet' || raw === 'wired') {
    return 'ethernet';
  }
  if (input.isConnected === true && !raw) {
    return 'unknown';
  }
  if (!raw || raw === 'unknown' || raw === 'none') {
    return input.isConnected === true ? 'unknown' : 'unknown';
  }
  if (raw === 'bluetooth' || raw === 'vpn' || raw === 'wimax' || raw === 'other') {
    return 'unknown';
  }
  return 'unknown';
}

export function compressionRatio(
  originalBytes: number | null | undefined,
  preparedBytes: number | null | undefined,
): number | null {
  if (
    originalBytes == null ||
    preparedBytes == null ||
    !(originalBytes > 0) ||
    !(preparedBytes >= 0)
  ) {
    return null;
  }
  return Math.round((preparedBytes / originalBytes) * 10000) / 10000;
}
