import type { DetectedCodeCandidate } from '../../core/codeDetectionConsolidator';

export const LOCAL_CODE_DETECTOR_VERSION = 'mlkit-barcode-1.0.0';

export type DeviceCapabilityStatus =
  | 'SUPPORTED'
  | 'UNSUPPORTED_ANDROID_VERSION'
  | 'SDK_UNAVAILABLE'
  | 'DISABLED';

type NativeBarcodeMod = {
  detectBarcodes?: (uri: string, formatsCsv: string) => Promise<Array<{ rawValue: string; format: string }>>;
  isBarcodeScannerAvailable?: () => Promise<boolean>;
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
    }));
}
