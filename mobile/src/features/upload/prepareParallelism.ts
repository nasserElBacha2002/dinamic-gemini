/**
 * Network-aware prepare parallelism for UploadQueue ticks (Phase 2).
 * Caps stay conservative to protect memory on mid-range Android devices.
 */
export type PrepareNetworkClass = 'wifi' | 'ethernet' | 'cellular' | 'unknown' | 'offline';

export function preparePerTickForNetwork(
  networkType: PrepareNetworkClass,
  options?: {
    readonly enabled?: boolean;
    readonly defaultPerTick?: number;
  },
): number {
  const fallback = options?.defaultPerTick ?? 2;
  if (options?.enabled === false) {
    return fallback;
  }
  switch (networkType) {
    case 'wifi':
    case 'ethernet':
      return 3;
    case 'cellular':
      return 2;
    case 'offline':
      return 1;
    default:
      return fallback;
  }
}

export function maxPreparedPendingForNetwork(
  networkType: PrepareNetworkClass,
  options?: { readonly enabled?: boolean },
): number {
  if (options?.enabled === false) {
    return 12;
  }
  switch (networkType) {
    case 'wifi':
    case 'ethernet':
      return 16;
    case 'cellular':
      return 10;
    case 'offline':
      return 8;
    default:
      return 12;
  }
}
