import { loadAppConfig, validateAppConfig } from '../config/env';
import { createLogger } from '../../core/logging';
import { getDatabase } from '../../database/database';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import { AuthService } from '../../features/auth/authService';
import { AisleService } from '../../features/aisles/aisleService';
import { CaptureService } from '../../features/capture/captureService';
import { InventoryService } from '../../features/inventories/inventoryService';
import { JobMonitor } from '../../features/processing/jobMonitor';
import { ProcessingService } from '../../features/processing/processingService';
import { AisleAssetsApi } from '../../features/upload/aisleAssetsApi';
import { UploadLimitsService } from '../../features/upload/uploadLimitsService';
import { UploadQueue } from '../../features/upload/uploadQueue';
import { createForegroundService } from '../../native/foregroundService';
import { queryMostRecentPhoto, queryNewPhotosSince, subscribeToGalleryChanges } from '../../native/mediaStore';
import { probeStability } from '../../native/stabilityProber';
import { ApiClient } from '../../services/api/apiClient';
import { createConnectivityService, type ConnectivityService } from '../../services/connectivity/connectivity';
import { secureTokenStorage } from '../../services/secureStorage/tokenStorage';

export interface AppServices {
  readonly configError: string | null;
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
  const uploadLimits = new UploadLimitsService(api, logger);
  const assetsApi = new AisleAssetsApi(api);
  const uploadQueue = new UploadQueue(captureRepo, assetsApi, uploadLimits, connectivity, logger);

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
  const jobMonitor = new JobMonitor(api, jobRepo, captureRepo, logger);

  if (!configError) {
    void uploadLimits.refresh();
    void uploadQueue.restoreAndStart();
    void jobMonitor.restorePendingJobs();
  }

  return {
    configError,
    api,
    auth: new AuthService(api, secureTokenStorage, logger),
    inventories: new InventoryService(api),
    aisles: new AisleService(api),
    capture,
    uploadQueue,
    uploadLimits,
    processing,
    jobMonitor,
    connectivity,
    async dispose() {
      capture.dispose();
      await uploadQueue.dispose();
      jobMonitor.dispose();
    },
  };
}
