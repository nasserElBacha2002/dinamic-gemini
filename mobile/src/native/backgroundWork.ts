import { Platform } from 'react-native';

import type { Logger } from '../core/logging';

/**
 * Minimal WorkManager bridge.
 * If the native module is absent (Expo Go / incomplete prebuild), falls back to no-op
 * and relies on JS queue restore on next app open.
 *
 * Unique work names:
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
}

type NativeScheduler = {
  scheduleUniqueWork?: (name: string, tag: string) => Promise<void>;
  cancelUniqueWork?: (name: string) => Promise<void>;
};

function tryNative(): NativeScheduler | null {
  if (Platform.OS !== 'android') {
    return null;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { requireOptionalNativeModule } = require('expo-modules-core') as {
      requireOptionalNativeModule: (name: string) => NativeScheduler | null;
    };
    const mod = requireOptionalNativeModule('CaptureForegroundService');
    if (mod && typeof mod.scheduleUniqueWork === 'function') {
      return mod;
    }
  } catch {
    return null;
  }
  return null;
}

export function createBackgroundWorkScheduler(logger: Logger): BackgroundWorkScheduler {
  const native = tryNative();
  const schedule = async (name: string, tag: string) => {
    if (native?.scheduleUniqueWork) {
      await native.scheduleUniqueWork(name, tag);
      logger.info('work_scheduled', { name, tag, mode: 'native' });
      return;
    }
    logger.info('work_scheduled', { name, tag, mode: 'noop_js_restore' });
  };
  const cancel = async (name: string) => {
    if (native?.cancelUniqueWork) {
      await native.cancelUniqueWork(name);
    }
  };
  return {
    scheduleUploadSession: (sessionId) => schedule(`upload-session-${sessionId}`, 'upload'),
    cancelUploadSession: (sessionId) => cancel(`upload-session-${sessionId}`),
    scheduleJobMonitor: (jobId) => schedule(`job-monitor-${jobId}`, 'job'),
    cancelJobMonitor: (jobId) => cancel(`job-monitor-${jobId}`),
    scheduleRemoteDelete: (assetId) => schedule(`remote-delete-${assetId}`, 'delete'),
  };
}
