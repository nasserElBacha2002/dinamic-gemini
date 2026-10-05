import {
  offlineAisleInstrumentationInvalid,
  runBenchmarkExportSequence,
  runBenchmarkOfflineAisleExport,
} from '../src/features/benchmark/benchmarkOfflineAisle';
import { createBenchmarkMetricsSink } from '../src/features/benchmark/benchmarkMetrics';
import type { OfflineAisleExportService } from '../src/features/offlineAisleExport/offlineAisleExportService';
import type { OfflineAisleExportPhaseEvent } from '../src/features/offlineAisleExport/offlineAisleExportService';
import { OFFLINE_AISLE_EXPORT_SCHEMA_VERSION } from '../src/features/offlineAisleExport/constants';

function sink() {
  return createBenchmarkMetricsSink({
    benchmarkRunId: 'run-1',
    processId: 'proc-1',
    resolvedClientSupplierId: 'sup',
    resolvedProfileName: 'andes',
  });
}

function exported(overrides: Record<string, unknown> = {}) {
  return {
    exportId: 'exp-1',
    fileUri: 'file:///docs/benchmark/run-1/bench.dinamic',
    fileName: 'bench.dinamic',
    captureCount: 3,
    assetCount: 3,
    completeness: 'COMPLETE' as const,
    payloadBytes: 1200,
    zipBytes: 4400,
    zipEntryCount: 5,
    schemaVersion: OFFLINE_AISLE_EXPORT_SCHEMA_VERSION,
    ...overrides,
  };
}

function mockService(impl?: OfflineAisleExportService['exportAisle']) {
  const shareExport = jest.fn(async () => undefined);
  const exportAisle = jest.fn(
    impl ??
      (async (options) => {
        const phases: OfflineAisleExportPhaseEvent['phase'][] = [
          'offline_prepare',
          'offline_asset_prepare',
          'offline_payload_build',
          'offline_integrity',
          'offline_validation',
          'offline_zip',
          'offline_total_export',
        ];
        for (const phase of phases) {
          options.onExportPhase?.({
            phase,
            monotonicStartMs: 1,
            durationMs: 2,
            success: true,
            extras: {
              payloadBytes: 1200,
              zipBytes: 4400,
              zipEntryCount: 5,
              captureCount: 3,
              assetCount: 3,
              schemaVersion: 2,
            },
          });
        }
        return exported();
      }),
  );
  return {
    exportAisle,
    shareExport,
  } as unknown as OfflineAisleExportService & {
    exportAisle: jest.Mock;
    shareExport: jest.Mock;
  };
}

describe('benchmark offline aisle helper', () => {
  test('behavioral lifecycle orders session export, offline export, then purge', async () => {
    const order: string[] = [];
    const exportSession = jest.fn(async () => {
      order.push('session_export_start');
      await Promise.resolve();
      order.push('session_export_end');
      return { exportId: 'session-export' };
    });
    const exportOfflineAisle = jest.fn(async () => {
      order.push('offline_export');
      return { exportId: 'offline-export' };
    });
    const purge = jest.fn(async () => {
      order.push('purge');
    });

    await runBenchmarkExportSequence({ exportSession, exportOfflineAisle });
    await purge();

    expect(exportSession).toHaveBeenCalledTimes(1);
    expect(exportOfflineAisle).toHaveBeenCalledTimes(1);
    expect(purge).toHaveBeenCalledTimes(1);
    expect(order).toEqual(['session_export_start', 'session_export_end', 'offline_export', 'purge']);
  });

  test('without flag does not export and preserves prior behavior', async () => {
    const service = mockService();
    const metrics = sink();
    const result = await runBenchmarkOfflineAisleExport({
      enabled: false,
      offlineAisleExport: service,
      inventoryId: 'inv',
      aisleId: 'aisle',
      sessionId: 'bench-sess-run-1',
      expectedCaptureCount: 3,
      outputDirectory: 'file:///docs/benchmark/run-1',
      sink: metrics,
    });
    expect(result).toBeNull();
    expect(service.exportAisle).not.toHaveBeenCalled();
    expect(service.shareExport).not.toHaveBeenCalled();
    expect(metrics.events.filter((e) => String(e.stage).startsWith('offline_'))).toHaveLength(0);
  });

  test('with flag executes exactly one offline export before caller cleanup', async () => {
    const service = mockService();
    const metrics = sink();
    const result = await runBenchmarkOfflineAisleExport({
      enabled: true,
      offlineAisleExport: service,
      inventoryId: 'inv',
      aisleId: 'aisle',
      sessionId: 'bench-sess-run-1',
      expectedCaptureCount: 3,
      outputDirectory: 'file:///docs/benchmark/run-1',
      sink: metrics,
    });
    expect(service.exportAisle).toHaveBeenCalledTimes(1);
    expect(service.exportAisle).toHaveBeenCalledWith({
      inventoryId: 'inv',
      aisleId: 'aisle',
      includeAssets: true,
      requireAssets: true,
      skipSessionPrepare: true,
      outputDirectory: 'file:///docs/benchmark/run-1',
      onExportPhase: expect.any(Function),
    });
    expect(service.shareExport).not.toHaveBeenCalled();
    expect(result).toMatchObject({
      captureCount: 3,
      zipBytes: 4400,
      zipEntryCount: 5,
      payloadBytes: 1200,
      schemaVersion: 2,
      includeAssets: true,
      requireAssets: true,
    });
    const offlineStages = metrics.events.filter((e) => String(e.stage).startsWith('offline_'));
    expect(offlineStages.map((e) => e.stage)).toEqual([
      'offline_prepare',
      'offline_asset_prepare',
      'offline_payload_build',
      'offline_integrity',
      'offline_validation',
      'offline_zip',
      'offline_total_export',
    ]);
    expect(offlineAisleInstrumentationInvalid(true, metrics.events)).toBe(false);
  });

  test('does not execute offline export twice', async () => {
    const service = mockService();
    const metrics = sink();
    await runBenchmarkOfflineAisleExport({
      enabled: true,
      offlineAisleExport: service,
      inventoryId: 'inv',
      aisleId: 'aisle',
      sessionId: 'sess',
      expectedCaptureCount: 3,
      outputDirectory: 'file:///docs/benchmark/run-1',
      sink: metrics,
    });
    expect(service.exportAisle).toHaveBeenCalledTimes(1);
  });

  test('offline export failure fails the helper', async () => {
    const service = mockService(async () => {
      throw Object.assign(new Error('EXPORT_IN_PROGRESS: busy'), { code: 'EXPORT_IN_PROGRESS' });
    });
    await expect(
      runBenchmarkOfflineAisleExport({
        enabled: true,
        offlineAisleExport: service,
        inventoryId: 'inv',
        aisleId: 'aisle',
        sessionId: 'sess',
        expectedCaptureCount: 3,
        outputDirectory: 'file:///docs/benchmark/run-1',
        sink: sink(),
      }),
    ).rejects.toMatchObject({ code: 'EXPORT_IN_PROGRESS' });
    expect(service.shareExport).not.toHaveBeenCalled();
  });

  test('package validation failure (capture count) fails the run', async () => {
    const service = mockService(async () => exported({ captureCount: 2 }));
    await expect(
      runBenchmarkOfflineAisleExport({
        enabled: true,
        offlineAisleExport: service,
        inventoryId: 'inv',
        aisleId: 'aisle',
        sessionId: 'sess',
        expectedCaptureCount: 3,
        outputDirectory: 'file:///docs/benchmark/run-1',
        sink: sink(),
      }),
    ).rejects.toMatchObject({ code: 'OFFLINE_AISLE_VALIDATION_FAILED' });
  });

  test('missing service fails when flag is on', async () => {
    await expect(
      runBenchmarkOfflineAisleExport({
        enabled: true,
        offlineAisleExport: null,
        inventoryId: 'inv',
        aisleId: 'aisle',
        sessionId: 'sess',
        expectedCaptureCount: 3,
        outputDirectory: 'file:///docs/benchmark/run-1',
        sink: sink(),
      }),
    ).rejects.toMatchObject({ code: 'OFFLINE_AISLE_EXPORT_DISABLED' });
  });

  test('instrumentation helper requires exactly one successful offline stage set', () => {
    expect(offlineAisleInstrumentationInvalid(false, [])).toBe(false);
    expect(
      offlineAisleInstrumentationInvalid(true, [
        { stage: 'offline_payload_build', success: true },
        { stage: 'offline_prepare', success: true },
        { stage: 'offline_asset_prepare', success: true },
        { stage: 'offline_integrity', success: true },
        { stage: 'offline_validation', success: true },
        { stage: 'offline_zip', success: true },
        { stage: 'offline_total_export', success: true },
      ]),
    ).toBe(false);
    expect(
      offlineAisleInstrumentationInvalid(true, [
        { stage: 'offline_payload_build', success: true },
        { stage: 'offline_prepare', success: true },
        { stage: 'offline_asset_prepare', success: true },
        { stage: 'offline_integrity', success: true },
        { stage: 'offline_validation', success: true },
        { stage: 'offline_zip', success: true },
        { stage: 'offline_total_export', success: false },
      ]),
    ).toBe(true);
    expect(
      offlineAisleInstrumentationInvalid(true, [
        { stage: 'offline_payload_build', success: true },
        { stage: 'offline_payload_build', success: true },
        { stage: 'offline_prepare', success: true },
        { stage: 'offline_asset_prepare', success: true },
        { stage: 'offline_integrity', success: true },
        { stage: 'offline_validation', success: true },
        { stage: 'offline_zip', success: true },
        { stage: 'offline_total_export', success: true },
      ]),
    ).toBe(true);
  });
});
