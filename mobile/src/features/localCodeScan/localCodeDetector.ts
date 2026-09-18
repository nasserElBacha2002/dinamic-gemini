import type { DetectedCodeCandidate } from '../../core/codeDetectionConsolidator';

/** Bump when native multipass/tile behavior changes so drafts re-scan. */
export const LOCAL_CODE_DETECTOR_VERSION = 'mlkit-barcode-1.1.0-multipass';

export type DeviceCapabilityStatus =
  | 'SUPPORTED'
  | 'UNSUPPORTED_ANDROID_VERSION'
  | 'SDK_UNAVAILABLE'
  | 'DISABLED';

type NativeBarcodeMod = {
  detectBarcodes?: (
    uri: string,
    formatsCsv: string,
  ) => Promise<Array<{ rawValue: string; format: string; boundingBox?: string }>>;
  isBarcodeScannerAvailable?: () => Promise<boolean>;
  setBarcodeScanConcurrency?: (n: number) => Promise<{
    configured?: number;
    active?: number;
    maxObserved?: number;
  }>;
  getBarcodeScanConcurrencyStats?: () => Promise<{
    configured?: number;
    active?: number;
    maxObserved?: number;
  }>;
  resetBarcodeScanConcurrencyStats?: () => Promise<{
    configured?: number;
    active?: number;
    maxObserved?: number;
  }>;
};

function platformOS(): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { Platform } = require('react-native') as { Platform: { OS: string } };
    return Platform.OS;
  } catch {
    return 'unknown';
  }
}

function resolveNative(): NativeBarcodeMod | null {
  try {
    if (platformOS() !== 'android') {
      return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { requireOptionalNativeModule } = require('expo-modules-core') as {
      requireOptionalNativeModule: (name: string) => NativeBarcodeMod | null;
    };
    return requireOptionalNativeModule('CaptureForegroundService');
  } catch {
    return null;
  }
}

/** Formats enabled for mobile shadow scan (subset of ML Kit / server). */
export const MOBILE_CODE_SCAN_FORMATS = [
  'QR_CODE',
  'CODE_128',
  'CODE_39',
  'EAN_13',
  'EAN_8',
  'UPC_A',
  'UPC_E',
] as const;

export async function evaluateLocalCodeScanCapability(input: {
  readonly flagEnabled: boolean;
}): Promise<DeviceCapabilityStatus> {
  if (!input.flagEnabled) {
    return 'DISABLED';
  }
  if (platformOS() !== 'android') {
    return 'UNSUPPORTED_ANDROID_VERSION';
  }
  const native = resolveNative();
  if (!native?.detectBarcodes) {
    return 'SDK_UNAVAILABLE';
  }
  try {
    if (native.isBarcodeScannerAvailable) {
      const ok = await native.isBarcodeScannerAvailable();
      if (!ok) {
        return 'SDK_UNAVAILABLE';
      }
    }
  } catch {
    return 'SDK_UNAVAILABLE';
  }
  return 'SUPPORTED';
}

export async function detectLocalBarcodes(uri: string): Promise<DetectedCodeCandidate[]> {
  const native = resolveNative();
  if (!native?.detectBarcodes) {
    throw new Error('SDK_UNAVAILABLE');
  }
  const formats = MOBILE_CODE_SCAN_FORMATS.join(',');
  const rows = await native.detectBarcodes(uri, formats);
  return (rows ?? [])
    .filter((r) => r && typeof r.rawValue === 'string' && r.rawValue.length > 0)
    .map((r, i) => ({
      rawValue: r.rawValue.slice(0, 512),
      symbology: String(r.format || 'UNKNOWN'),
      detectionIndex: i,
      boundingBox: typeof r.boundingBox === 'string' && r.boundingBox.trim() ? r.boundingBox : null,
    }));
}

/** Phase 4: configure native ML Kit concurrent scan slots (1|2). */
export async function setNativeBarcodeScanConcurrency(n: 1 | 2): Promise<{
  readonly configured: number;
  readonly applied: boolean;
  readonly available: boolean;
}> {
  if (n !== 1 && n !== 2) {
    throw Object.assign(new Error('NATIVE_SCAN_CONCURRENCY_INVALID'), {
      code: 'NATIVE_SCAN_CONCURRENCY_INVALID',
    });
  }
  const native = resolveNative();
  if (!native?.setBarcodeScanConcurrency) {
    return { configured: n, applied: false, available: false };
  }
  const stats = await native.setBarcodeScanConcurrency(n);
  return {
    configured: Number(stats?.configured ?? n),
    applied: true,
    available: true,
  };
}

/** Phase 4: read native concurrent-scan stats when the module exposes them. */
export async function getNativeBarcodeScanConcurrencyStats(): Promise<{
  readonly available: boolean;
  readonly configured: number | null;
  readonly active: number | null;
  readonly maxObserved: number | null;
}> {
  const native = resolveNative();
  if (!native?.getBarcodeScanConcurrencyStats) {
    return { available: false, configured: null, active: null, maxObserved: null };
  }
  try {
    const stats = await native.getBarcodeScanConcurrencyStats();
    return {
      available: true,
      configured: typeof stats?.configured === 'number' ? stats.configured : null,
      active: typeof stats?.active === 'number' ? stats.active : null,
      maxObserved: typeof stats?.maxObserved === 'number' ? stats.maxObserved : null,
    };
  } catch {
    return { available: false, configured: null, active: null, maxObserved: null };
  }
}

/** Phase 4: reset native peak counters before every isolated run. */
export async function resetNativeBarcodeScanConcurrencyStats(): Promise<{
  readonly available: boolean;
  readonly configured: number | null;
  readonly active: number | null;
  readonly maxObserved: number | null;
}> {
  const native = resolveNative();
  if (!native?.resetBarcodeScanConcurrencyStats) {
    return { available: false, configured: null, active: null, maxObserved: null };
  }
  const stats = await native.resetBarcodeScanConcurrencyStats();
  return {
    available: true,
    configured: typeof stats?.configured === 'number' ? stats.configured : null,
    active: typeof stats?.active === 'number' ? stats.active : null,
    maxObserved: typeof stats?.maxObserved === 'number' ? stats.maxObserved : null,
  };
}
