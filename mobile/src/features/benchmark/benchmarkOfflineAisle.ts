import { OFFLINE_AISLE_EXPORT_SCHEMA_VERSION } from '../offlineAisleExport/constants';
import type {
  ExportedOfflineAisle,
  OfflineAisleExportPhaseEvent,
  OfflineAisleExportService,
} from '../offlineAisleExport/offlineAisleExportService';
import type { BenchmarkMetricsSink } from './benchmarkMetrics';

export const BENCHMARK_OFFLINE_AISLE_STAGES = [
  'offline_prepare',
  'offline_asset_prepare',
  'offline_payload_build',
  'offline_integrity',
  'offline_validation',
  'offline_zip',
  'offline_total_export',
] as const;

export type BenchmarkOfflineAisleSummary = {
  readonly exportId: string;
  readonly fileName: string;
  readonly captureCount: number;
  readonly assetCount: number;
  readonly payloadBytes: number;
  readonly zipBytes: number;
  readonly zipEntryCount: number;
  readonly schemaVersion: typeof OFFLINE_AISLE_EXPORT_SCHEMA_VERSION;
  readonly includeAssets: true;
  readonly requireAssets: true;
};

export async function runBenchmarkExportSequence<T>(input: {
  readonly exportSession: () => Promise<unknown>;
  readonly exportOfflineAisle: () => Promise<T>;
}): Promise<T> {
  await input.exportSession();
  return input.exportOfflineAisle();
}

function emitOfflinePhase(
  sink: BenchmarkMetricsSink,
  sessionId: string,
  event: OfflineAisleExportPhaseEvent,
): void {
  sink.emit({
    sessionId,
    stage: event.phase,
    monotonicStartMs: event.monotonicStartMs,
    durationMs: event.durationMs,
    executionContext: 'js',
    success: event.success,
    errorCode: event.errorCode ?? null,
    ...(event.extras
      ? {
          extras: event.extras,
          inputBytes:
            typeof event.extras.payloadBytes === 'number' ? event.extras.payloadBytes : null,
          outputBytes: typeof event.extras.zipBytes === 'number' ? event.extras.zipBytes : null,
        }
      : {}),
  });
}

function fail(code: string, message: string): never {
  throw Object.assign(new Error(message), { code });
}

/**
 * Independent Offline Aisle v2 measurement after session CSV export.
 * Does not re-run admission, staging, or scan. Never shares the package.
 */
export async function runBenchmarkOfflineAisleExport(input: {
  readonly enabled: boolean;
  readonly offlineAisleExport: OfflineAisleExportService | null;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly sessionId: string;
  readonly expectedCaptureCount: number;
  readonly outputDirectory: string;
  readonly sink: BenchmarkMetricsSink;
}): Promise<BenchmarkOfflineAisleSummary | null> {
  if (!input.enabled) {
    return null;
  }
  if (!input.offlineAisleExport) {
    fail('OFFLINE_AISLE_EXPORT_DISABLED', 'offlineAisleExport is not wired');
  }

  const exported: ExportedOfflineAisle = await input.offlineAisleExport.exportAisle({
    inventoryId: input.inventoryId,
    aisleId: input.aisleId,
    includeAssets: true,
    requireAssets: true,
    skipSessionPrepare: true,
    outputDirectory: input.outputDirectory,
    onExportPhase: (event) => emitOfflinePhase(input.sink, input.sessionId, event),
  });

  if (exported.schemaVersion !== OFFLINE_AISLE_EXPORT_SCHEMA_VERSION) {
    fail(
      'OFFLINE_AISLE_VALIDATION_FAILED',
      `schema_version=${exported.schemaVersion} expected=${OFFLINE_AISLE_EXPORT_SCHEMA_VERSION}`,
    );
  }
  if (exported.captureCount !== input.expectedCaptureCount) {
    fail(
      'OFFLINE_AISLE_VALIDATION_FAILED',
      `capture_count=${exported.captureCount} expected=${input.expectedCaptureCount}`,
    );
  }

  return {
    exportId: exported.exportId,
    fileName: exported.fileName,
    captureCount: exported.captureCount,
    assetCount: exported.assetCount,
    payloadBytes: exported.payloadBytes,
    zipBytes: exported.zipBytes,
    zipEntryCount: exported.zipEntryCount,
    schemaVersion: exported.schemaVersion,
    includeAssets: true,
    requireAssets: true,
  };
}

export function offlineAisleInstrumentationInvalid(
  enabled: boolean,
  events: readonly { readonly stage: string; readonly success: boolean }[],
): boolean {
  if (!enabled) return false;
  for (const stage of BENCHMARK_OFFLINE_AISLE_STAGES) {
    const rows = events.filter((e) => e.stage === stage);
    if (rows.length !== 1 || rows[0]!.success !== true) {
      return true;
    }
  }
  return false;
}
