import { loadAppConfig, validateAppConfig, type AppConfig } from '../config/env';
import { createLogger, type Logger } from '../../core/logging';
import { getDatabase } from '../../database/database';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import { AuthService } from '../../features/auth/authService';
import { AisleService } from '../../features/aisles/aisleService';
import { CaptureService } from '../../features/capture/captureService';
import { InventoryService } from '../../features/inventories/inventoryService';
import { JobMonitor } from '../../features/processing/jobMonitor';
import { ProcessingService } from '../../features/processing/processingService';
import {
  buildDiagnosticBundle,
  diagnosticToShareText,
  type DiagnosticBundle,
} from '../../features/support/diagnosticExport';
import { runHealthChecks, type HealthCheckResult } from '../../features/support/healthChecks';
import { cleanupTransformTemps, getStorageStatus } from '../../features/support/storageCleanup';
import { AisleAssetsApi } from '../../features/upload/aisleAssetsApi';
import { UploadLimitsService } from '../../features/upload/uploadLimitsService';
import { UploadQueue } from '../../features/upload/uploadQueue';
import {
  createBackgroundWorkScheduler,
  type BackgroundWorkScheduler,
} from '../../native/backgroundWork';
import { createForegroundService } from '../../native/foregroundService';
import { queryMostRecentPhoto, queryNewPhotosSince, subscribeToGalleryChanges } from '../../native/mediaStore';
import { probeStability } from '../../native/stabilityProber';
import { ApiClient } from '../../services/api/apiClient';
import { createConnectivityService, type ConnectivityService } from '../../services/connectivity/connectivity';
import { secureTokenStorage } from '../../services/secureStorage/tokenStorage';

export interface AppServices {
  readonly config: AppConfig;
  readonly configError: string | null;
  readonly logger: Logger;
  readonly auth: AuthService;
  readonly inventories: InventoryService;
  readonly aisles: AisleService;
  readonly capture: CaptureService;
  readonly api: ApiClient;
  readonly uploadQueue: UploadQueue;
  readonly uploadLimits: UploadLimitsService;
  readonly processing: ProcessingService;
  readonly jobMonitor: JobMonitor;
  readonly connectivity: ConnectivityService;
  readonly backgroundWork: BackgroundWorkScheduler;
  exportDiagnostic(): Promise<DiagnosticBundle>;
  diagnosticShareText(bundle: DiagnosticBundle): string;
  runHealthChecks(): Promise<readonly HealthCheckResult[]>;
  getStorageStatus(): ReturnType<typeof getStorageStatus>;
  dispose(): Promise<void>;
}

export async function createAppServices(onAuthExpired: () => void): Promise<AppServices> {
  const config = loadAppConfig();
  const configError = validateAppConfig(config);
  const logger = createLogger();
  const api = new ApiClient({
    config,
    tokenStorage: secureTokenStorage,
    logger,
    onAuthExpired,
  });
  const db = await getDatabase();
  const captureRepo = new CaptureRepository(db);
  const jobRepo = new ProcessingJobRepository(db);
  const connectivity = createConnectivityService();
  const backgroundWork = createBackgroundWorkScheduler(logger);
  const uploadLimits = new UploadLimitsService(api, logger);
  const assetsApi = new AisleAssetsApi(api);
  const uploadQueue = new UploadQueue(
    captureRepo,
    assetsApi,
    uploadLimits,
    connectivity,
    logger,
    {
      flags: config.flags,
      backgroundWork: config.flags.workManagerScheduling ? backgroundWork : null,
    },
  );

  const capture = new CaptureService(captureRepo, createForegroundService(), logger, {
    mediaStore: {
      queryMostRecentPhoto,
      queryNewPhotosSince,
      subscribeToGalleryChanges,
    },
    stabilityProber: {
      probe: (uri) => probeStability(uri),
    },
    onPhotoStable: (sessionId, photoId) => {
      void uploadQueue.enqueuePhoto(sessionId, photoId);
    },
  });

  const processing = new ProcessingService(api, captureRepo, jobRepo, uploadQueue, assetsApi, logger);
  const jobMonitor = new JobMonitor(api, jobRepo, captureRepo, logger, {
    backgroundPolling: config.flags.backgroundJobPolling,
    backgroundWork: config.flags.workManagerScheduling ? backgroundWork : null,
  });

  if (!configError) {
    void uploadLimits.refresh();
    void uploadQueue.restoreAndStart();
    void jobMonitor.restorePendingJobs();
    void cleanupTransformTemps(logger);
    void getStorageStatus().then((s) => {
      if (s.lowSpace) {
        logger.warn('error', { code: 'CAPTURE_STORAGE_LOW', freeBytes: s.freeBytes });
      }
    });
  }

  return {
    config,
    configError,
    logger,
    api,
    auth: new AuthService(api, secureTokenStorage, logger, async () => {
      await backgroundWork.cancelAllTracked();
      await uploadQueue.pause('logout');
    }),
    inventories: new InventoryService(api),
    aisles: new AisleService(api, logger),
    capture,
    uploadQueue,
    uploadLimits,
    processing,
    jobMonitor,
    connectivity,
    backgroundWork,
    exportDiagnostic: () =>
      buildDiagnosticBundle({
        config,
        captureRepo,
        jobRepo,
        uploadQueue,
        connectivity,
      }),
    diagnosticShareText: diagnosticToShareText,
    runHealthChecks: () =>
      runHealthChecks({
        config,
        api,
        tokenStorage: secureTokenStorage,
        connectivity,
        logger,
        probeSqlite: async () => {
          await captureRepo.listActivitySessions();
        },
        probeMediaStore: async () => {
          await queryMostRecentPhoto();
        },
      }),
    getStorageStatus,
    async dispose() {
      capture.dispose();
      await uploadQueue.dispose();
      jobMonitor.dispose();
      await backgroundWork.cancelAllTracked();
    },
  };
}
