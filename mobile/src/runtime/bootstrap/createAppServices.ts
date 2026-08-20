import { loadAppConfig, validateAppConfig, type AppConfig } from '../config/env';
import { createLogger, type Logger } from '../../core/logging';
import { getDatabase, consumeDatabaseRecoveryFlag } from '../../database/database';
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
import { OrderedCaptureApi } from '../../features/upload/orderedCaptureApi';
import { UploadLimitsService } from '../../features/upload/uploadLimitsService';
import { UploadQueue } from '../../features/upload/uploadQueue';
import { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import { LocalCsvExportRepository } from '../../database/repositories/localCsvExportRepository';
import { LocalCsvExportService } from '../../features/localCsv/localCsvExportService';
import { getOrCreateInstallationId } from '../../shared/installationId';
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
import { OfflineOperationRepository } from '../../database/repositories/offlineOperationRepository';
import { AisleRevisionApi } from '../../features/aisleRevision/aisleRevisionApi';
import { AisleRevisionService } from '../../features/aisleRevision/aisleRevisionService';
import { AisleRevisionDraftRepository } from '../../database/repositories/aisleRevisionDraftRepository';
import {
  OfflineOperationScheduler,
  createOfflineOperationFacade,
  buildDirectedExecutorMap,
  createOfflineAutoEnqueue,
  subscribeAuthState,
  type OfflineOperationFacade,
} from '../../features/offlineOperations';
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
  /** True when SQLite was deleted/recreated due to corruption on this boot. */
  readonly databaseRecoveredFromCorruption: boolean;
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
  readonly localCsvExport: LocalCsvExportService | null;
  readonly confirmLocalResult: Pick<
    ConfirmLocalResultService,
    | 'isEnabled'
    | 'getLatestDraftForPhoto'
    | 'resolveSource'
    | 'confirm'
    | 'confirmResolvedDraftsForSession'
  >;
  readonly preliminarySync: PreliminaryDetectionSyncService;
  readonly authoritativeLocalSync: AuthoritativeLocalResultSyncService;
  readonly authoritativeAisleFinalization: AuthoritativeAisleFinalizationService;
  readonly serverReprocess: ServerReprocessService;
  readonly aisleRevision: AisleRevisionService;
  readonly reconciliation: ReconciliationQueryService;
  readonly connectivity: ConnectivityService;
  readonly backgroundWork: BackgroundWorkScheduler;
  readonly backgroundUpload: BackgroundUploadScheduler;
  /** Phase 9: null when `mobileOfflineOperations` is off. */
  readonly offlineOperations: OfflineOperationFacade | null;
  readonly offlineScheduler: OfflineOperationScheduler | null;
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
  if (config.isDevelopment && config.apiBaseUrl) {
    logger.info('mobile_api_base_url', { apiBaseUrl: config.apiBaseUrl });
  }
  const tokenStorage = createMirroredTokenStorage(secureTokenStorage, config);
  const api = new ApiClient({
    config,
    tokenStorage,
    logger,
    onAuthExpired,
  });
  const db = await getDatabase();
  const databaseRecoveredFromCorruption = consumeDatabaseRecoveryFlag();
  if (databaseRecoveredFromCorruption) {
    logger.warn('recovery', {
      code: 'LOCAL_DB_CORRUPTED',
      message: 'Local SQLite recreated after corruption',
    });
  }
  const captureRepo = new CaptureRepository(db);
  const jobRepo = new ProcessingJobRepository(db);
  const localDetectionDrafts = new LocalDetectionDraftRepository(db);
  const confirmedLocalResults = new ConfirmedLocalResultRepository(db);
  const localCsvExportRepo = new LocalCsvExportRepository(db);
  const installationId = await getOrCreateInstallationId();
  const aisleFinalizationIntents = new AisleFinalizationIntentRepository(db);
  const serverReprocessIntents = new ServerReprocessIntentRepository(db);
  const aisleRevisionDrafts = new AisleRevisionDraftRepository(db);
  const offlineOpsRepo = new OfflineOperationRepository(db);
  const offlineOpsEnabled = config.flags.mobileOfflineOperations === true;
  let offlineAutoEnqueue: ReturnType<typeof createOfflineAutoEnqueue> | null = null;
  const connectivity = createConnectivityService();
  const backgroundWork = createBackgroundWorkScheduler(logger, config.flags);
  const backgroundUpload = asBackgroundUploadScheduler(backgroundWork);
  const uploadLimits = new UploadLimitsService(api, logger);
  const assetsApi = new AisleAssetsApi(api);
  const orderedCaptureApi = new OrderedCaptureApi(api);
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
    onActivePositionChanged: async (sessionId, state) => {
      await captureRepo.updateActivePositionJson(sessionId, JSON.stringify(state));
    },
  });
  void localCodeScan.recoverStaleDrafts().catch(() => {
    // best-effort recovery after process death
  });
  const localCsvExport =
    config.flags.mobileCsvExport !== false
      ? new LocalCsvExportService({
          captureRepo,
          draftRepo: localDetectionDrafts,
          confirmedRepo: confirmedLocalResults,
          exportRepo: localCsvExportRepo,
          deviceId: installationId,
          companyId: null,
          clientId: null,
          enabled: true,
          localCodeScan,
          localCodeScanEnabled: config.flags.mobileLocalCodeScan === true,
        })
      : null;
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
  const confirmLocalResultBase = new ConfirmLocalResultService(
    config.flags,
    confirmedLocalResults,
    localDetectionDrafts,
  );
  const confirmLocalResult = {
    isEnabled: () => confirmLocalResultBase.isEnabled(),
    getLatestDraftForPhoto: (id: string) => confirmLocalResultBase.getLatestDraftForPhoto(id),
    resolveSource: confirmLocalResultBase.resolveSource.bind(confirmLocalResultBase),
    confirmResolvedDraftsForSession: (
      args: Parameters<ConfirmLocalResultService['confirmResolvedDraftsForSession']>[0],
    ) => confirmLocalResultBase.confirmResolvedDraftsForSession(args),
    confirm: async (args: Parameters<ConfirmLocalResultService['confirm']>[0]) => {
      const row = await confirmLocalResultBase.confirm(args);
      const session = await captureRepo.getSession(args.captureSessionId);
      if (session && offlineOpsEnabled) {
        // assigned after offline bootstrap — call via delayed tick
        void (async () => {
          // wait until offlineAutoEnqueue is wired (same tick as bootstrap)
          await Promise.resolve();
          await offlineAutoEnqueue?.onResultConfirmed({
            resultId: row.id,
            capturePhotoId: row.capture_photo_id,
            sessionId: args.captureSessionId,
            inventoryId: session.inventory_id,
            aisleId: session.aisle_id,
            contentHash: `${row.id}:${row.row_version}:${row.confirmed_internal_code}`,
          });
        })();
      }
      return row;
    },
  };
  if (config.flags.mobileAuthoritativeLocalCodeScan && !offlineOpsEnabled) {
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
  const aisleRevision = new AisleRevisionService(
    new AisleRevisionApi(api),
    config.flags.mobileAisleRevisions ? aisleRevisionDrafts : null,
    connectivity,
    {
      mobileAisleRevisions: config.flags.mobileAisleRevisions,
      mobileAisleHistory: config.flags.mobileAisleHistory,
      serverAisleRevisions: config.flags.serverAisleRevisions,
      serverAisleRollback: config.flags.serverAisleRollback,
    },
  );
  // Legacy drains — suppressed when unified offline_operations scheduler owns them.
  if (config.flags.serverReprocessOfflineQueue && !offlineOpsEnabled) {
    const drain = () => {
      void serverReprocess.drainPending().catch(() => undefined);
    };
    connectivity.subscribe((state) => {
      if (state === 'online') {
        drain();
      }
    });
    drain();
  }
  if (
    config.flags.mobileAisleRevisions &&
    config.flags.serverAisleRevisions &&
    !offlineOpsEnabled
  ) {
    const syncDrafts = () => {
      void aisleRevision.syncPendingDrafts().catch(() => undefined);
    };
    connectivity.subscribe((state) => {
      if (state === 'online') {
        syncDrafts();
      }
    });
    syncDrafts();
  }
  if (
    config.flags.authoritativeFinalizationOfflineQueue &&
    config.flags.mobileAuthoritativeAisleFinalization &&
    !offlineOpsEnabled
  ) {
    const drainFinalize = () => {
      void authoritativeAisleFinalization.drainPending().catch(() => undefined);
    };
    connectivity.subscribe((state) => {
      if (state === 'online') {
        drainFinalize();
      }
    });
    drainFinalize();
  }
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
      orderedCapture: orderedCaptureApi,
      authoritativeExclusion: config.flags.mobileAuthoritativeAisleFinalization
        ? authoritativeAisleFinalization
        : null,
    },
  );

  let photoStableChain: Promise<void> = Promise.resolve();

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
      // Serialize upload + offline enqueue: parallel fire-and-forget stampedes SQLite
      // (database is locked) when many photos stabilize during "Finalizar captura".
      // With localCompletion/csvExport, server upload is deferred until explicit policy
      // (NOW / WHEN_CONNECTED) or completeReview → uploading — not on every stable photo.
      // Local CODE_SCAN still runs when upload is deferred so ZIP export has drafts.
      photoStableChain = photoStableChain
        .then(async () => {
          await uploadQueue.enqueuePhoto(sessionId, photoId);
          const session = await captureRepo.getSession(sessionId);
          const localZipMode =
            config.flags.localCompletion === true || config.flags.mobileCsvExport === true;
          const policy = session?.upload_policy;
          const status = session?.status;
          const allowOfflineUpload =
            !localZipMode ||
            policy === 'NOW' ||
            policy === 'WHEN_CONNECTED' ||
            status === 'uploading' ||
            status === 'upload_review';
          if (allowOfflineUpload) {
            await offlineAutoEnqueue?.onPhotoPersisted(sessionId, photoId);
          } else if (config.flags.mobileLocalCodeScan === true) {
            await uploadQueue.rescanPhotoForLocalReview(photoId).catch(() => undefined);
          }
        })
        .catch((error) => {
          logger.warn('recovery', {
            where: 'on_photo_stable_chain',
            message: error instanceof Error ? error.message : String(error),
          });
        });
    },
    observability: obsWire,
    finishInstrumentation: config.flags.captureFinishInstrumentation,
    finishSafeMediaCheck: config.flags.captureFinishSafeMediaCheck,
    sessionFreeze: config.flags.captureSessionFreeze,
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
    { flags: config.flags, confirmed: confirmedLocalResults, drafts: localDetectionDrafts },
    orderedCaptureApi,
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

  let offlineScheduler: OfflineOperationScheduler | null = null;
  let offlineOperations: OfflineOperationFacade | null = null;
  if (offlineOpsEnabled) {
    offlineOperations = createOfflineOperationFacade({ repo: offlineOpsRepo, logger });
    const executors = buildDirectedExecutorMap({
      wakeUploadQueue: async () => {
        void uploadQueue.restoreAndStart();
        await backgroundWork.scheduleUploadQueue(true);
      },
      capture: captureRepo,
      confirmed: confirmedLocalResults,
      authoritativeSync: authoritativeLocalSync,
      finalization: authoritativeAisleFinalization,
      finalizationIntents: aisleFinalizationIntents,
      serverReprocess,
      serverReprocessIntents: config.flags.serverReprocessOfflineQueue
        ? serverReprocessIntents
        : null,
      aisleRevision,
      aisleRevisionDrafts: config.flags.mobileAisleRevisions ? aisleRevisionDrafts : null,
      processing,
    });
    offlineScheduler = new OfflineOperationScheduler({
      repo: offlineOpsRepo,
      logger,
      executors,
      getHasNetwork: () => connectivity.getState() !== 'offline',
      getHasAuth: async () => Boolean(await tokenStorage.getAccessToken()),
      concurrency: 2,
      onWakeNative: async () => {
        if (config.flags.mobileOfflineWorkManager) {
          await backgroundWork.scheduleOfflineOperations(false);
        }
      },
    });
    offlineAutoEnqueue = createOfflineAutoEnqueue({
      enabled: true,
      facade: offlineOperations,
      scheduler: offlineScheduler,
      capture: captureRepo,
      logger,
    });
    offlineScheduler.start();
    subscribeAuthState((state) => {
      if (state === 'authenticated') {
        void offlineScheduler?.onAuthRestored();
      } else {
        void offlineScheduler?.onAuthMissing();
      }
    });
    connectivity.subscribe((state) => {
      if (state === 'online') {
        void offlineScheduler?.tick();
      }
    });
    if (config.flags.mobileOfflineWorkManager) {
      void backgroundWork.scheduleOfflineOperations(false);
    }
    const cutoff = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
    void offlineOpsRepo
      .purgeRetention({
        completedBeforeIso: cutoff,
        failedBeforeIso: cutoff,
        eventBeforeIso: cutoff,
      })
      .catch(() => undefined);
    logger.info('recovery', {
      obs: true,
      obs_name: 'offline_recovery_started',
      mode: 'offline_operations_scheduler',
    });
  }

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
    void processing.recoverStuckStartingSessions().catch(() => {
      // best-effort — never block bootstrap
    });
    if (config.flags.mobilePreliminaryDetectionSync) {
      void preliminarySync.syncPending().catch(() => {
        // best-effort — never block bootstrap
      });
    }
    if (config.flags.mobileAuthoritativeLocalCodeScan && !offlineOpsEnabled) {
      void authoritativeLocalSync.syncPending().catch(() => {
        // best-effort — never block bootstrap
      });
    }
    if (offlineOpsEnabled) {
      void offlineScheduler?.recoverAndTick().catch(() => undefined);
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
    databaseRecoveredFromCorruption,
    logger,
    api,
    auth: new AuthService(
      api,
      tokenStorage,
      logger,
      async () => {
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
        offlineScheduler?.stop();
      },
      async () => {
        await offlineScheduler?.onAuthRestored();
      },
    ),
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
    localCsvExport,
    confirmLocalResult,
    preliminarySync,
    authoritativeLocalSync,
    authoritativeAisleFinalization,
    serverReprocess,
    aisleRevision,
    reconciliation,
    connectivity,
    backgroundWork,
    backgroundUpload,
    offlineOperations,
    offlineScheduler,
    exportDiagnostic: async () => {
      let offlineOperationsSummary = null;
      if (offlineOpsEnabled) {
        try {
          const active = await offlineOpsRepo.listActive(500);
          const byStatus: Record<string, number> = {};
          for (const row of active) {
            byStatus[row.status] = (byStatus[row.status] ?? 0) + 1;
          }
          offlineOperationsSummary = {
            enabled: true,
            activeCount: active.length,
            byStatus,
          };
        } catch {
          offlineOperationsSummary = { enabled: true, activeCount: -1, byStatus: {} };
        }
      } else {
        offlineOperationsSummary = { enabled: false, activeCount: 0, byStatus: {} };
      }
      return buildDiagnosticBundle({
        config,
        captureRepo,
        jobRepo,
        uploadQueue,
        connectivity,
        observabilityStore: observability.store,
        offlineOperations: offlineOperationsSummary,
      });
    },
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
      offlineScheduler?.stop();
      capture.dispose();
      await uploadQueue.dispose();
      jobMonitor.dispose();
      await observability.dispose();
      await backgroundWork.cancelAllTracked();
    },
  };
}
