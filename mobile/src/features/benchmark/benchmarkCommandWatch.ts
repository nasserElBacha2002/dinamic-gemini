import * as FileSystem from 'expo-file-system';

import type { AppConfig } from '../../runtime/config/resolveAppConfig';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { AppServices } from '../../runtime/bootstrap/createAppServices';
import type { SessionArtifactPurgeCoordinator } from '../exportPrep/sessionArtifactPurgeCoordinator';
import { BENCHMARK_NAMESPACE_PREFIX } from './authorizedIds';
import {
  BenchmarkRunner,
  createBenchmarkProcessId,
  type BenchmarkCommand,
  type BenchmarkStatusDocument,
} from './benchmarkRunner';

const INBOX_RELATIVE = `${BENCHMARK_NAMESPACE_PREFIX}/inbox/command.json`;
const POLL_MS = 1500;

export type BenchmarkBootstrapHooks = {
  readonly captureRepo: CaptureRepository;
  readonly sessionPurge: SessionArtifactPurgeCoordinator | null;
};

/**
 * Debug-only file inbox: Mac pushes command.json via adb/run-as;
 * this watch polls and executes BenchmarkRunner.
 */
export function startBenchmarkCommandWatch(
  services: AppServices,
  hooks: BenchmarkBootstrapHooks,
): () => void {
  if (!isBenchmarkWatchAllowed(services.config)) {
    return () => undefined;
  }
  const doc = FileSystem.documentDirectory;
  if (!doc) {
    return () => undefined;
  }

  const processId = createBenchmarkProcessId();
  let stopped = false;
  let busy = false;
  let timer: ReturnType<typeof setInterval> | null = null;
  const inboxPath = `${doc}${INBOX_RELATIVE}`;

  const tick = async () => {
    if (stopped || busy) return;
    busy = true;
    try {
      const info = await FileSystem.getInfoAsync(inboxPath);
      if (!info.exists) return;
      const raw = await FileSystem.readAsStringAsync(inboxPath);
      const command = JSON.parse(raw) as BenchmarkCommand;
      await FileSystem.deleteAsync(inboxPath, { idempotent: true });
      const runner = new BenchmarkRunner({
        environment: services.config.environment,
        isDevelopment: services.config.isDevelopment,
        processId,
        captureRepo: hooks.captureRepo,
        catalogRepo: services.catalogRepo,
        recognitionRepo: services.offlineRecognition.repo,
        draftRepo: services.localDetectionDrafts,
        aisles: services.aisles,
        exportPrepQueue: services.exportPrepQueue,
        localCsvExport: services.localCsvExport,
        profileResolver: services.offlineRecognition.resolver,
        sessionPurge: hooks.sessionPurge,
        documentDirectory: doc,
        localCodeScan: services.localCodeScan ?? null,
      });
      const status = await runner.run(command);
      await writeWatchAck(doc, status);
    } catch (error) {
      const message = error instanceof Error ? error.message.slice(0, 200) : 'watch_error';
      try {
        await FileSystem.writeAsStringAsync(
          `${doc}${BENCHMARK_NAMESPACE_PREFIX}/inbox/last-error.json`,
          JSON.stringify({ at: new Date().toISOString(), message }),
        );
      } catch {
        // ignore
      }
    } finally {
      busy = false;
    }
  };

  timer = setInterval(() => {
    void tick();
  }, POLL_MS);
  void tick();

  return () => {
    stopped = true;
    if (timer) clearInterval(timer);
  };
}

async function writeWatchAck(doc: string, status: BenchmarkStatusDocument): Promise<void> {
  await FileSystem.writeAsStringAsync(
    `${doc}${BENCHMARK_NAMESPACE_PREFIX}/inbox/last-status.json`,
    JSON.stringify(status, null, 2),
  );
}

export function isBenchmarkWatchAllowed(config: AppConfig): boolean {
  return config.isDevelopment && config.environment !== 'production';
}
