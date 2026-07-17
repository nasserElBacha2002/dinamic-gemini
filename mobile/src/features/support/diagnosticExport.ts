import type { AppConfig } from '../../runtime/config/resolveAppConfig';
import { sharedLogBuffer } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import type { UploadQueue } from '../upload/uploadQueue';
import type { ConnectivityService } from '../../services/connectivity/connectivity';

export interface DiagnosticBundle {
  readonly exportedAt: string;
  readonly app: {
    readonly versionName: string;
    readonly versionCode: number;
    readonly gitSha: string;
    readonly buildTime: string;
    readonly environment: string;
  };
  readonly connectivity: string;
  readonly sessions: readonly Record<string, unknown>[];
  readonly jobs: readonly Record<string, unknown>[];
  readonly uploadSnapshot: Record<string, unknown>;
  readonly logs: readonly Record<string, unknown>[];
  readonly flags: Record<string, unknown>;
}

/**
 * Builds a redacted diagnostic JSON payload for support.
 * Never includes tokens, passwords, photos, or API keys.
 */
export async function buildDiagnosticBundle(input: {
  readonly config: AppConfig;
  readonly captureRepo: CaptureRepository;
  readonly jobRepo: ProcessingJobRepository;
  readonly uploadQueue: UploadQueue;
  readonly connectivity: ConnectivityService;
}): Promise<DiagnosticBundle> {
  const sessions = await input.captureRepo.listActivitySessions();
  const jobs = await input.jobRepo.listNonTerminal();
  const snapshot = input.uploadQueue.getSnapshot();
  return {
    exportedAt: new Date().toISOString(),
    app: {
      versionName: input.config.versionName,
      versionCode: input.config.versionCode,
      gitSha: input.config.gitSha,
      buildTime: input.config.buildTime,
      environment: input.config.environment,
    },
    connectivity: input.connectivity.getState(),
    sessions: sessions.map((s) => ({
      id: s.id,
      inventory_id: s.inventory_id,
      aisle_id: s.aisle_id,
      status: s.status,
      upload_status: s.upload_status,
      processing_status: s.processing_status,
      backend_job_id: s.backend_job_id,
      updated_at: s.updated_at,
    })),
    jobs: jobs.map((j) => ({
      id: j.id,
      backend_job_id: j.backend_job_id,
      status: j.status,
      remote_status: j.remote_status,
      capture_session_id: j.capture_session_id,
    })),
    uploadSnapshot: {
      pauseReason: snapshot.pauseReason,
      activeRequests: snapshot.activeRequests,
      sessions: snapshot.sessions,
    },
    logs: sharedLogBuffer.snapshot().map((r) => ({
      ts: r.ts,
      level: r.level,
      event: r.event,
      fields: r.fields,
    })),
    flags: { ...input.config.flags },
  };
}

export function diagnosticToShareText(bundle: DiagnosticBundle): string {
  return JSON.stringify(bundle, null, 2);
}
