import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as FileSystem from 'expo-file-system';

/**
 * Device/host environment snapshot for benchmark artifacts.
 * Missing platform APIs are reported with *UnavailableReason — never silently omitted.
 */
export type BenchmarkEnvironmentSnapshot = {
  readonly appVersion: string | null;
  readonly appBuild: string | null;
  readonly jsEngine: string | null;
  readonly batteryLevelStart: number | null;
  readonly batteryLevelEnd: number | null;
  readonly batteryCharging: boolean | null;
  readonly batteryUnavailableReason: string | null;
  readonly thermalStatusStart: string | null;
  readonly thermalStatusEnd: string | null;
  readonly thermalStatusUnavailableReason: string | null;
  readonly freeStorageBytesStart: number | null;
  readonly freeStorageBytesEnd: number | null;
  readonly freeStorageUnavailableReason: string | null;
  readonly totalFixtureBytes: number | null;
  readonly fixtureCount: number | null;
  /**
   * ExportPrepQueue worker slots. Phase 4 A/B keeps this at 1 while varying
   * scannerConcurrency independently — do not couple the two knobs.
   */
  readonly exportPrepMaxWorkers: number | null;
  /** Local/native barcode scan concurrency (Phase 4 A/B variable). */
  readonly scannerConcurrency: number | null;
  /** Peak JS LocalCodeScanStrategy in-flight scans observed during the run. */
  readonly maxObservedScannerConcurrency: number | null;
  /** Peak native ML Kit in-flight scans when getBarcodeScanConcurrencyStats exists. */
  readonly maxObservedNativeScannerConcurrency: number | null;
  readonly deviceManufacturer: string | null;
  readonly deviceModel: string | null;
  readonly androidRelease: string | null;
  readonly androidSdk: number | null;
  readonly gitSha: string | null;
  readonly dirty: boolean | null;
  readonly gitMetaUnavailableReason: string | null;
};

function detectJsEngine(): string {
  const g = globalThis as { HermesInternal?: unknown };
  if (g.HermesInternal != null) return 'hermes';
  return 'jsc_or_unknown';
}

async function freeStorageBytes(): Promise<{
  bytes: number | null;
  reason: string | null;
}> {
  try {
    if (typeof FileSystem.getFreeDiskStorageAsync === 'function') {
      const bytes = await FileSystem.getFreeDiskStorageAsync();
      return { bytes: typeof bytes === 'number' ? bytes : null, reason: null };
    }
    return { bytes: null, reason: 'getFreeDiskStorageAsync_unavailable' };
  } catch (error) {
    return {
      bytes: null,
      reason: error instanceof Error ? error.message.slice(0, 120) : 'free_storage_error',
    };
  }
}

export async function captureBenchmarkEnvironmentStart(input: {
  readonly totalFixtureBytes: number;
  readonly fixtureCount: number;
  readonly exportPrepMaxWorkers: number;
  readonly scannerConcurrency: number;
  readonly maxObservedScannerConcurrency?: number | null;
  readonly maxObservedNativeScannerConcurrency?: number | null;
}): Promise<BenchmarkEnvironmentSnapshot> {
  const free = await freeStorageBytes();
  const constants = Platform.constants as
    | { Manufacturer?: string; Brand?: string; Model?: string; Release?: string; Version?: number }
    | undefined;

  return {
    appVersion:
      Constants.expoConfig?.version ??
      Constants.nativeAppVersion ??
      null,
    appBuild:
      Constants.expoConfig?.android?.versionCode != null
        ? String(Constants.expoConfig.android.versionCode)
        : Constants.nativeBuildVersion ?? null,
    jsEngine: detectJsEngine(),
    batteryLevelStart: null,
    batteryLevelEnd: null,
    batteryCharging: null,
    batteryUnavailableReason: 'expo-battery_not_installed',
    thermalStatusStart: null,
    thermalStatusEnd: null,
    thermalStatusUnavailableReason: 'android_thermal_api_not_wired',
    freeStorageBytesStart: free.bytes,
    freeStorageBytesEnd: null,
    freeStorageUnavailableReason: free.reason,
    totalFixtureBytes: input.totalFixtureBytes,
    fixtureCount: input.fixtureCount,
    exportPrepMaxWorkers: input.exportPrepMaxWorkers,
    scannerConcurrency: input.scannerConcurrency,
    maxObservedScannerConcurrency: input.maxObservedScannerConcurrency ?? null,
    maxObservedNativeScannerConcurrency: input.maxObservedNativeScannerConcurrency ?? null,
    deviceManufacturer: constants?.Manufacturer ?? constants?.Brand ?? null,
    deviceModel: constants?.Model ?? null,
    androidRelease: Platform.OS === 'android' ? String(constants?.Release ?? Platform.Version) : null,
    androidSdk: Platform.OS === 'android' && typeof constants?.Version === 'number' ? constants.Version : null,
    gitSha: null,
    dirty: null,
    gitMetaUnavailableReason: 'git_meta_filled_by_mac_coordinator',
  };
}

export async function finalizeBenchmarkEnvironment(
  start: BenchmarkEnvironmentSnapshot,
  overrides?: {
    readonly maxObservedScannerConcurrency?: number | null;
    readonly maxObservedNativeScannerConcurrency?: number | null;
  },
): Promise<BenchmarkEnvironmentSnapshot> {
  const free = await freeStorageBytes();
  return {
    ...start,
    freeStorageBytesEnd: free.bytes,
    freeStorageUnavailableReason: free.reason ?? start.freeStorageUnavailableReason,
    // Battery/thermal still unavailable without native modules.
    batteryLevelEnd: null,
    thermalStatusEnd: null,
    maxObservedScannerConcurrency:
      overrides?.maxObservedScannerConcurrency ?? start.maxObservedScannerConcurrency,
    maxObservedNativeScannerConcurrency:
      overrides?.maxObservedNativeScannerConcurrency ??
      start.maxObservedNativeScannerConcurrency,
  };
}
