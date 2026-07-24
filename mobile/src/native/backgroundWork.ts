import type { FeatureFlags } from '../core/featureFlags';
import type { Logger } from '../core/logging';
import {
  UNIQUE_UPLOAD_QUEUE_WORK,
  uniqueUploadSessionWorkName as leaseSessionWorkName,
} from '../core/uploadLease';

/**
 * Background work policy (Phase 2):
 * When `backgroundUploadWorker` is on, schedules real Android WorkManager unique work.
 * When off, no-op (JS UploadQueue + SQLite restore on open — legacy behavior).
 */
export interface BackgroundWorkScheduler {
  scheduleUploadSession(sessionId: string): Promise<void>;
  cancelUploadSession(sessionId: string): Promise<void>;
  scheduleJobMonitor(jobId: string): Promise<void>;
  cancelJobMonitor(jobId: string): Promise<void>;
  scheduleRemoteDelete(assetId: string): Promise<void>;
  cancelAllTracked(): Promise<void>;
  scheduleUploadQueue(expedited?: boolean): Promise<void>;
  /** Clear native AuthVault queuePaused and reschedule WorkManager (no-op if flag off). */
  resumeUploadQueue(): Promise<void>;
  getStatus(): Promise<BackgroundUploadStatus>;
}

export interface BackgroundUploadStatus {
  readonly uniqueWorkState: string;
  readonly pendingPrepared: number;
  readonly running: boolean;
  readonly mode: 'native' | 'noop';
  readonly queuePaused?: boolean;
  readonly vaultAvailable?: boolean;
}

export interface BackgroundUploadScheduler {
  schedule(): Promise<void>;
  cancel(): Promise<void>;
  getStatus(): Promise<BackgroundUploadStatus>;
}

export function uniqueUploadSessionWorkName(sessionId: string): string {
  return leaseSessionWorkName(sessionId);
}

export function uniqueJobMonitorWorkName(jobId: string): string {
  return `job-monitor-${jobId}`;
}

export function uniqueRemoteDeleteWorkName(assetId: string): string {
  return `remote-delete-${assetId}`;
}

type NativeBg = {
  scheduleUniqueWork: (name: string, tag: string) => Promise<void>;
  cancelUniqueWork: (name: string) => Promise<void>;
  cancelAllUploadWork?: () => Promise<void>;
  scheduleUploadQueue?: (expedited: boolean) => Promise<void>;
  getBackgroundUploadStatus?: () => Promise<Record<string, unknown>>;
  syncUploadAuth?: (params: Record<string, unknown>) => Promise<boolean>;
  clearUploadAuth?: () => Promise<void>;
  pauseUploadQueue?: () => Promise<void>;
  resumeUploadQueue?: () => Promise<void>;
};

function resolveNative(): NativeBg | null {
  try {
    // Lazy require so core Jest suites can import name helpers without RN.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { Platform } = require('react-native') as { Platform: { OS: string } };
    if (Platform.OS !== 'android') {
      return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { requireOptionalNativeModule } = require('expo-modules-core') as {
      requireOptionalNativeModule: (name: string) => NativeBg | null;
    };
    const mod = requireOptionalNativeModule('CaptureForegroundService');
    if (mod && typeof mod.scheduleUniqueWork === 'function') {
      return mod;
    }
  } catch {
    /* module missing / non-RN test runtime */
  }
  return null;
}

export function createBackgroundWorkScheduler(
  logger: Logger,
  flags?: Pick<
    FeatureFlags,
    'backgroundUploadWorker' | 'workManagerScheduling'
  > | null,
): BackgroundWorkScheduler {
  const tracked = new Set<string>();
  const native = resolveNative();
  const workerEnabled = flags?.backgroundUploadWorker === true;

  const scheduleNative = async (name: string, tag: string) => {
    tracked.add(name);
    if (workerEnabled && native) {
      await native.scheduleUniqueWork(name, tag);
      logger.info('work_scheduled', { name, tag, mode: 'native_workmanager' });
      return;
    }
    logger.info('work_scheduled', { name, tag, mode: 'noop_js_restore_on_open' });
  };

  const cancelNative = async (name: string) => {
    tracked.delete(name);
    if (workerEnabled && native) {
      await native.cancelUniqueWork(name);
      logger.info('work_scheduled', { name, tag: 'cancel', mode: 'native_cancel' });
      return;
    }
    logger.info('work_scheduled', { name, tag: 'cancel', mode: 'noop_cancel' });
  };

  return {
    // Per-session names still accepted for API stability; native maps them to the global queue.
    scheduleUploadSession: (_sessionId) => scheduleNative(UNIQUE_UPLOAD_QUEUE_WORK, 'upload'),
    cancelUploadSession: async (_sessionId) => {
      // Cancel work only — never sticky-pause the vault (that blocked later schedules).
      if (workerEnabled && native?.cancelAllUploadWork) {
        await native.cancelAllUploadWork();
        logger.info('work_scheduled', {
          name: UNIQUE_UPLOAD_QUEUE_WORK,
          tag: 'cancel',
          mode: 'native_cancel_queue',
        });
        return;
      }
      await cancelNative(UNIQUE_UPLOAD_QUEUE_WORK);
    },
    scheduleJobMonitor: (jobId) => scheduleNative(uniqueJobMonitorWorkName(jobId), 'job'),
    cancelJobMonitor: (jobId) => cancelNative(uniqueJobMonitorWorkName(jobId)),
    scheduleRemoteDelete: (assetId) => scheduleNative(uniqueRemoteDeleteWorkName(assetId), 'delete'),
    scheduleUploadQueue: async (expedited = false) => {
      tracked.add(UNIQUE_UPLOAD_QUEUE_WORK);
      if (workerEnabled && native?.scheduleUploadQueue) {
        await native.scheduleUploadQueue(expedited);
        logger.info('work_scheduled', {
          name: UNIQUE_UPLOAD_QUEUE_WORK,
          tag: 'upload-queue',
          mode: 'native_workmanager',
        });
        return;
      }
      await scheduleNative(UNIQUE_UPLOAD_QUEUE_WORK, 'upload-queue');
    },
    resumeUploadQueue: async () => {
      if (workerEnabled && native?.resumeUploadQueue) {
        await native.resumeUploadQueue();
        logger.info('work_scheduled', {
          name: UNIQUE_UPLOAD_QUEUE_WORK,
          tag: 'resume',
          mode: 'native_resume_queue',
        });
      }
    },
    cancelAllTracked: async () => {
      if (workerEnabled && native?.cancelAllUploadWork) {
        await native.cancelAllUploadWork();
      }
      for (const name of [...tracked]) {
        await cancelNative(name);
      }
    },
    getStatus: async () => {
      if (workerEnabled && native?.getBackgroundUploadStatus) {
        const s = await native.getBackgroundUploadStatus();
        return {
          uniqueWorkState: String(s.uniqueWorkState ?? 'UNKNOWN'),
          pendingPrepared: Number(s.pendingPrepared ?? -1),
          running: Boolean(s.running),
          mode: 'native' as const,
          queuePaused: Boolean(s.queuePaused),
          vaultAvailable: s.vaultAvailable !== false,
        };
      }
      return {
        uniqueWorkState: 'NONE',
        pendingPrepared: -1,
        running: false,
        mode: 'noop' as const,
      };
    },
  };
}

export function asBackgroundUploadScheduler(
  work: BackgroundWorkScheduler,
): BackgroundUploadScheduler {
  return {
    schedule: () => work.scheduleUploadQueue(true),
    cancel: () => work.cancelAllTracked(),
    getStatus: () => work.getStatus(),
  };
}

/**
 * Sync auth/config into native EncryptedSharedPreferences for the upload worker.
 * Returns false if the vault could not commit — callers must not schedule WorkManager.
 */
export async function syncNativeUploadAuth(input: {
  readonly accessToken: string | null;
  readonly refreshToken: string | null;
  readonly apiBaseUrl: string;
  readonly apiKey: string | null;
  readonly flags: FeatureFlags;
  readonly sqliteDbPath?: string | null;
}): Promise<boolean> {
  const native = resolveNative();
  if (!native?.syncUploadAuth) {
    return true;
  }
  const ok = await native.syncUploadAuth({
    accessToken: input.accessToken,
    refreshToken: input.refreshToken,
    apiBaseUrl: input.apiBaseUrl,
    apiKey: input.apiKey,
    allowMobileData: input.flags.allowMobileDataUploads,
    fgsEnabled: input.flags.backgroundUploadForegroundService,
    workerEnabled: input.flags.backgroundUploadWorker,
    rebootResume: input.flags.backgroundUploadRebootResume,
    sqliteDbPath: input.sqliteDbPath ?? null,
  });
  return ok !== false;
}

export async function clearNativeUploadAuth(): Promise<void> {
  const native = resolveNative();
  if (!native?.clearUploadAuth) {
    return;
  }
  await native.clearUploadAuth();
}
