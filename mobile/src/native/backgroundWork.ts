import type { Logger } from '../core/logging';

/**
 * Background work policy (honest):
 * Native WorkManager does not drain the JS upload queue after process death.
 * Unique work names are documented for a future native worker; current schedule is a no-op
 * that only logs. Recovery = app reopen → SQLite restore.
 *
 * Unique work names (reserved):
 * - upload-session-{sessionId}
 * - job-monitor-{jobId}
 * - remote-delete-{assetId}
 */
export interface BackgroundWorkScheduler {
  scheduleUploadSession(sessionId: string): Promise<void>;
  cancelUploadSession(sessionId: string): Promise<void>;
  scheduleJobMonitor(jobId: string): Promise<void>;
  cancelJobMonitor(jobId: string): Promise<void>;
  scheduleRemoteDelete(assetId: string): Promise<void>;
  cancelAllTracked(): Promise<void>;
}

export function uniqueUploadSessionWorkName(sessionId: string): string {
  return `upload-session-${sessionId}`;
}

export function uniqueJobMonitorWorkName(jobId: string): string {
  return `job-monitor-${jobId}`;
}

export function uniqueRemoteDeleteWorkName(assetId: string): string {
  return `remote-delete-${assetId}`;
}

export function createBackgroundWorkScheduler(logger: Logger): BackgroundWorkScheduler {
  const tracked = new Set<string>();
  const schedule = async (name: string, tag: string) => {
    tracked.add(name);
    logger.info('work_scheduled', { name, tag, mode: 'noop_js_restore_on_open' });
  };
  const cancel = async (name: string) => {
    tracked.delete(name);
    logger.info('work_scheduled', { name, tag: 'cancel', mode: 'noop_cancel' });
  };
  return {
    scheduleUploadSession: (sessionId) => schedule(uniqueUploadSessionWorkName(sessionId), 'upload'),
    cancelUploadSession: (sessionId) => cancel(uniqueUploadSessionWorkName(sessionId)),
    scheduleJobMonitor: (jobId) => schedule(uniqueJobMonitorWorkName(jobId), 'job'),
    cancelJobMonitor: (jobId) => cancel(uniqueJobMonitorWorkName(jobId)),
    scheduleRemoteDelete: (assetId) => schedule(uniqueRemoteDeleteWorkName(assetId), 'delete'),
    cancelAllTracked: async () => {
      for (const name of [...tracked]) {
        await cancel(name);
      }
    },
  };
}
