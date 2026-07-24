import { loadAppConfig, validateAppConfig, type AppConfig } from '../config/env';
import { createLogger, type Logger } from '../../core/logging';
import { getDatabase } from '../../database/database';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import { AuthService } from '../../features/auth/authService';
import { AisleService } from '../../features/aisles/aisleService';
import { CaptureService } from '../../features/capture/captureService';
import { ClientService } from '../../features/clients/clientService';
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
import { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import { AisleFinalizationIntentRepository } from '../../database/repositories/aisleFinalizationIntentRepository';
import { LocalCodeScanStrategy } from '../../features/localCodeScan/localCodeScanStrategy';
import { PreliminaryDetectionApi } from '../../features/preliminarySync/preliminaryDetectionApi';
import { PreliminaryDetectionSyncService } from '../../features/preliminarySync/preliminaryDetectionSyncService';
import { AuthoritativeLocalResultApi } from '../../features/authoritativeLocalResult/authoritativeLocalResultApi';
import { AuthoritativeLocalResultSyncService } from '../../features/authoritativeLocalResult/authoritativeLocalResultSyncService';
import { ConfirmLocalResultService } from '../../features/authoritativeLocalResult/confirmLocalResultService';
import { AuthoritativeAisleFinalizationApi } from '../../features/authoritativeAisleFinalization/authoritativeAisleFinalizationApi';
import { AuthoritativeAisleFinalizationService } from '../../features/authoritativeAisleFinalization/authoritativeAisleFinalizationService';
import { ServerReprocessApi } from '../../features/serverReprocess/serverReprocessApi';
import { ServerReprocessService } from '../../features/serverReprocess/serverReprocessService';
import { ServerReprocessIntentRepository } from '../../database/repositories/serverReprocessIntentRepository';
import { createId } from '../../shared/createId';
import { PreliminaryReconciliationApi } from '../../features/preliminaryReconciliation/preliminaryReconciliationApi';
import { ReconciliationQueryService } from '../../features/preliminaryReconciliation/reconciliationQueryService';
import {
  buildBaselineReport,
  createObservabilityStack,
  rowsToParsedEvents,
  type BaselineReport,
} from '../../observability';
import {
  asBackgroundUploadScheduler,
  clearNativeUploadAuth,
  createBackgroundWorkScheduler,
  syncNativeUploadAuth,
  type BackgroundUploadScheduler,
  type BackgroundWorkScheduler,
} from '../../native/backgroundWork';
import { createForegroundService } from '../../native/foregroundService';
import { queryMostRecentPhoto, queryNewPhotosSince, subscribeToGalleryChanges } from '../../native/mediaStore';
import { probeStability } from '../../native/stabilityProber';
import { ApiClient } from '../../services/api/apiClient';
import { createConnectivityService, type ConnectivityService } from '../../services/connectivity/connectivity';
import { secureTokenStorage, type TokenStorage } from '../../services/secureStorage/tokenStorage';

function createMirroredTokenStorage(base: TokenStorage, config: AppConfig): TokenStorage {
  const sync = async () => {
    const ok = await syncNativeUploadAuth({
      accessToken: await base.getAccessToken(),
      refreshToken: await base.getRefreshToken(),
      apiBaseUrl: config.apiBaseUrl,
      apiKey: config.apiKey,
      flags: config.flags,
    });
    if (!ok) {
      // Vault unavailable — leave JS queue able to run when app is open; native will not schedule.
    }
  };
  return {
    getAccessToken: () => base.getAccessToken(),
    getRefreshToken: () => base.getRefreshToken(),
    async saveTokens(tokens) {
      await base.saveTokens(tokens);
      await sync();
    },
    async clear() {
      await base.clear();
      await clearNativeUploadAuth();
    },
  };
}

export interface AppServices {
  readonly config: AppConfig;
  readonly configError: string | null;
  readonly logger: Logger;
  readonly auth: AuthService;
  readonly inventories: InventoryService;
  readonly clients: ClientService;
  readonly aisles: AisleService;
  readonly capture: CaptureService;
  readonly api: ApiClient;
  readonly uploadQueue: UploadQueue;
  readonly uploadLimits: UploadLimitsService;
  readonly processing: ProcessingService;
  readonly jobMonitor: JobMonitor;
  readonly localDetectionDrafts: LocalDetectionDraftRepository;
  readonly confirmedLocalResults: ConfirmedLocalResultRepository;
  readonly confirmLocalResult: ConfirmLocalResultService;
  readonly preliminarySync: PreliminaryDetectionSyncService;
  readonly authoritativeLocalSync: AuthoritativeLocalResultSyncService;
  readonly authoritativeAisleFinalization: AuthoritativeAisleFinalizationService;
  readonly serverReprocess: ServerReprocessService;
  readonly reconciliation: ReconciliationQueryService;
  readonly connectivity: ConnectivityService;
  readonly backgroundWork: BackgroundWorkScheduler;
  readonly backgroundUpload: BackgroundUploadScheduler;
  exportDiagnostic(): Promise<DiagnosticBundle>;
  diagnosticShareText(bundle: DiagnosticBundle): string;
  exportObservabilityBaseline(): Promise<BaselineReport | null>;
  runHealthChecks(): Promise<readonly HealthCheckResult[]>;
  getStorageStatus(): ReturnType<typeof getStorageStatus>;
  dispose(): Promise<void>;
}

export async function createAppServices(onAuthExpired: () => void): Promise<AppServices> {
  const config = loadAppConfig();
  const configError = validateAppConfig(config);
  const logger = createLogger();
  const tokenStorage = createMirroredTokenStorage(secureTokenStorage, config);
  const api = new ApiClient({
    config,
    tokenStorage,
    logger,
    onAuthExpired,
  });
  const db = await getDatabase();
  const captureRepo = new CaptureRepository(db);
  const jobRepo = new ProcessingJobRepository(db);
  const localDetectionDrafts = new LocalDetectionDraftRepository(db);
  const confirmedLocalResults = new ConfirmedLocalResultRepository(db);
  const aisleFinalizationIntents = new AisleFinalizationIntentRepository(db);
  const serverReprocessIntents = new ServerReprocessIntentRepository(db);
  const connectivity = createConnectivityService();
  const backgroundWork = createBackgroundWorkScheduler(logger, config.flags);
  const backgroundUpload = asBackgroundUploadScheduler(backgroundWork);
  const uploadLimits = new UploadLimitsService(api, logger);
  const assetsApi = new AisleAssetsApi(api);
  const observability = createObservabilityStack({
    enabled: config.flags.uploadObservabilityEnabled,
    logger,
    db,
  });
  const obsWire =
    config.flags.uploadObservabilityEnabled
      ? { reporter: observability.reporter, marks: observability.marks }
      : null;
  const localCodeScan = new LocalCodeScanStrategy({
    drafts: localDetectionDrafts,
    reporter: obsWire?.reporter ?? null,
  });
  void localCodeScan.recoverStaleDrafts().catch(() => {
    // best-effort recovery after process death
  });
  const preliminaryApi = new PreliminaryDetectionApi(api);
  const preliminarySync = new PreliminaryDetectionSyncService({
    flags: config.flags,
    drafts: localDetectionDrafts,
    capture: captureRepo,
    api: preliminaryApi,
    logger,
    reporter: obsWire?.reporter ?? null,
    connectivity,
  });
  const reconciliationApi = new PreliminaryReconciliationApi(api);
  const reconciliation = new ReconciliationQueryService({
    api: reconciliationApi,
    drafts: localDetectionDrafts,
    flags: config.flags,
    logger,
    observability: obsWire?.reporter ?? null,
  });
  if (config.flags.mobilePreliminaryDetectionSync) {
    preliminarySync.startScheduler();
  }
  const authoritativeApi = new AuthoritativeLocalResultApi(api);
  const authoritativeLocalSync = new AuthoritativeLocalResultSyncService({
    flags: config.flags,
    confirmed: confirmedLocalResults,
    capture: captureRepo,
    api: authoritativeApi,
    logger,
    reporter: obsWire?.reporter ?? null,
    connectivity,
  });
  const confirmLocalResult = new ConfirmLocalResultService(
    config.flags,
    confirmedLocalResults,
    localDetectionDrafts,
  );
  if (config.flags.mobileAuthoritativeLocalCodeScan) {
    authoritativeLocalSync.startScheduler();
  }
  const authoritativeAisleFinalization = new AuthoritativeAisleFinalizationService({
    flags: config.flags,
    api: new AuthoritativeAisleFinalizationApi(api),
    capture: captureRepo,
    confirmed: confirmedLocalResults,
    intents: aisleFinalizationIntents,
    connectivity,
    logger,
    createId,
  });
  const serverReprocess = new ServerReprocessService(
    new ServerReprocessApi(api),
    config.flags.serverReprocessOfflineQueue ? serverReprocessIntents : null,
    config.flags,
  );
  const useNativeBg =
    config.flags.backgroundUploadWorker === true || config.flags.workManagerScheduling === true;
  const uploadQueue = new UploadQueue(
    captureRepo,
    assetsApi,
    uploadLimits,
    connectivity,
    logger,
    {
      flags: config.flags,
      backgroundWork: useNativeBg ? backgroundWork : null,
      observability: obsWire,
      localCodeScan,
      preliminarySync,
      authoritativeSync: authoritativeLocalSync,
      authoritativeExclusion: config.flags.mobileAuthoritativeAisleFinalization
        ? authoritativeAisleFinalization
        : null,
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
    observability: obsWire,
  });

  const processing = new ProcessingService(
    api,
    captureRepo,
    jobRepo,
    uploadQueue,
    assetsApi,
    logger,
    obsWire
      ? { reporter: obsWire.reporter, marks: obsWire.marks, connectivity }
      : null,
    { flags: config.flags, confirmed: confirmedLocalResults },
  );
  const jobMonitor = new JobMonitor(api, jobRepo, captureRepo, logger, {
    backgroundPolling: config.flags.backgroundJobPolling,
    backgroundWork: config.flags.workManagerScheduling || config.flags.backgroundUploadWorker
      ? backgroundWork
      : null,
    observability: obsWire,
    flags: config.flags,
    localDrafts: localDetectionDrafts,
    reconciliation,
  });

  if (!configError) {
    void uploadLimits.refresh();
    void syncNativeUploadAuth({
      accessToken: null,
      refreshToken: null,
      apiBaseUrl: config.apiBaseUrl,
      apiKey: config.apiKey,
      flags: config.flags,
    }).then(async (synced) => {
      if (!synced) {
        logger.warn('error', { code: 'AUTH_VAULT_UNAVAILABLE' });
        return;
      }
      const access = await tokenStorage.getAccessToken();
      const refresh = await tokenStorage.getRefreshToken();
      if (access) {
        const ok = await syncNativeUploadAuth({
          accessToken: access,
          refreshToken: refresh,
          apiBaseUrl: config.apiBaseUrl,
          apiKey: config.apiKey,
          flags: config.flags,
        });
        if (ok && config.flags.backgroundUploadWorker) {
          void backgroundWork.scheduleUploadQueue(false);
        }
      }
    });
    void uploadQueue.restoreAndStart();
    void jobMonitor.restorePendingJobs();
    if (config.flags.mobilePreliminaryDetectionSync) {
      void preliminarySync.syncPending().catch(() => {
        // best-effort — never block bootstrap
      });
    }
    if (config.flags.mobileAuthoritativeLocalCodeScan) {
      void authoritativeLocalSync.syncPending().catch(() => {
        // best-effort — never block bootstrap
      });
    }
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
    auth: new AuthService(api, tokenStorage, logger, async () => {
      await backgroundWork.cancelAllTracked();
      await clearNativeUploadAuth();
      await uploadQueue.pause('logout');
      try {
        await localDetectionDrafts.deleteAll();
        await confirmedLocalResults.deleteAll();
      } catch {
        // best-effort — drafts must not survive logout
      }
      preliminarySync.stopScheduler();
      authoritativeLocalSync.stopScheduler();
    }),
    inventories: new InventoryService(api),
    clients: new ClientService(api),
    aisles: new AisleService(api, logger),
    capture,
    uploadQueue,
    uploadLimits,
    processing,
    jobMonitor,
    localDetectionDrafts,
    confirmedLocalResults,
    confirmLocalResult,
    preliminarySync,
    authoritativeLocalSync,
    authoritativeAisleFinalization,
    serverReprocess,
    reconciliation,
    connectivity,
    backgroundWork,
    backgroundUpload,
    exportDiagnostic: () =>
      buildDiagnosticBundle({
        config,
        captureRepo,
        jobRepo,
        uploadQueue,
        connectivity,
        observabilityStore: observability.store,
      }),
    diagnosticShareText: diagnosticToShareText,
    exportObservabilityBaseline: async () => {
      if (!observability.store) {
        return null;
      }
      const rows = await observability.store.listRecent(5000);
      return buildBaselineReport(rowsToParsedEvents(rows));
    },
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
      preliminarySync.stopScheduler();
      authoritativeLocalSync.stopScheduler();
      capture.dispose();
      await uploadQueue.dispose();
      jobMonitor.dispose();
      await observability.dispose();
      await backgroundWork.cancelAllTracked();
    },
  };
}
