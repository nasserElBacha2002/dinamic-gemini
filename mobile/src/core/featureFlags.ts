export interface FeatureFlags {
  readonly allowMobileDataUploads: boolean;
  /**
   * When true (default), convert HEIC/HEIF to JPEG before upload.
   * When false, upload HEIC as-is (backend worker can normalize).
   */
  readonly heicConvertToJpeg: boolean;
  /** Legacy gate for scheduling unique work names (kept for JobMonitor). */
  readonly workManagerScheduling: boolean;
  readonly advancedReconciliation: boolean;
  readonly backgroundJobPolling: boolean;
  readonly aisleDeviceLock: boolean;
  /** Phase 0 upload/process observability (kill switch: set DINAMIC_FLAG_UPLOAD_OBS=0). */
  readonly uploadObservabilityEnabled: boolean;
  /** Phase 0: emit capture.finish_* stage events (safe; default on). */
  readonly captureFinishInstrumentation: boolean;
  /** Phase 1: light MediaStore check before skipping finish rescan (default on). */
  readonly captureFinishSafeMediaCheck: boolean;
  /** Phase 1: persist capture freeze watermark on finish (default on). */
  readonly captureSessionFreeze: boolean;
  /** Phase 2: debounce UploadQueue emit/refreshCachedSessions (default on). */
  readonly uploadIncrementalSnapshots: boolean;
  /** Phase 2: network-aware prepare parallelism (default on). */
  readonly uploadPrepareParallelism: boolean;
  /** Phase 3: allow closing capture locally without upload/process (default on). */
  readonly localCompletion: boolean;
  /** Phase 4: offline local CSV export (default on). */
  readonly mobileCsvExport: boolean;
  /** Phase 5: client may call server CSV import APIs (default false until server flag on). */
  readonly serverCsvImport: boolean;
  /** Phase 6: classify local vs server result conflicts (default on). */
  readonly localRemoteReconciliation: boolean;
  /** Phase 1: proactive max-edge dimension cap during prepare. */
  readonly uploadDimensionCap: boolean;
  /** Phase 1: profile/network JPEG quality instead of legacy fixed qualities. */
  readonly uploadAdaptiveQuality: boolean;
  /** Phase 1: network-aware upload concurrency (still capped). */
  readonly uploadAdaptiveConcurrency: boolean;
  /** Phase 1: abort in-flight multipart when cancelPhoto runs. */
  readonly uploadAbortEnabled: boolean;
  /** Phase 2: native WorkManager upload worker. */
  readonly backgroundUploadWorker: boolean;
  /** Phase 2: promote long uploads to Foreground Service notification. */
  readonly backgroundUploadForegroundService: boolean;
  /** Phase 2: allow WorkManager to resume after device reboot. */
  readonly backgroundUploadRebootResume: boolean;
  /** Phase 3: local CODE_SCAN shadow detection (hard opt-in; default false). */
  readonly mobileLocalCodeScan: boolean;
  /** Phase 3: attempt shadow compare when a reliable mapping exists. */
  readonly mobileLocalCodeScanShadowCompare: boolean;
  /** Phase 4: sync local drafts to server as diagnostic evidence (default false). */
  readonly mobilePreliminaryDetectionSync: boolean;
  /** Phase 5: show server reconciliation outcomes (default false). */
  readonly mobilePreliminaryReconciliationView: boolean;
  /** Phase 5: allow JobMonitor to trigger server reconcile enqueue (default false). */
  readonly mobilePreliminaryReconciliationTrigger: boolean;
  /** Authoritative local CODE_SCAN: operator-confirmed results sync (default false). */
  readonly mobileAuthoritativeLocalCodeScan: boolean;
  /** Authoritative local CODE_SCAN: review screen before upload (default false). */
  readonly mobileLocalResultReview: boolean;
  /** Phase 6: authoritative aisle finalization without remote reprocess (default false). */
  readonly mobileAuthoritativeAisleFinalization: boolean;
  /** Phase 6: persist offline finalization intent (default false). */
  readonly authoritativeFinalizationOfflineQueue: boolean;
  /** Phase 7: optional server reprocess action (default false). */
  readonly mobileServerReprocess: boolean;
  /** Phase 7: proposal review / adoption UI (default false). */
  readonly mobileServerReprocessReview: boolean;
  /** Phase 7: persist offline reprocess request intent (default false). */
  readonly serverReprocessOfflineQueue: boolean;
  /** Phase 8: mobile aisle correction / revision UX (default false). */
  readonly mobileAisleRevisions: boolean;
  /** Phase 8: mobile aisle revision history screen (default false). */
  readonly mobileAisleHistory: boolean;
  /** Phase 8: call server aisle revision APIs (default false). */
  readonly serverAisleRevisions: boolean;
  /** Phase 8: allow rollback from history (default false). */
  readonly serverAisleRollback: boolean;
  /** Phase 9: unified durable offline_operations ledger + scheduler (default false). */
  readonly mobileOfflineOperations: boolean;
  /** Phase 9: schedule WorkManager wake for offline recovery (default false). */
  readonly mobileOfflineWorkManager: boolean;
  /** Phase 9: route finalization intents through offline_operations (default false). */
  readonly mobileOfflineFinalization: boolean;
  /** Phase 9: route revision sync/apply through offline_operations (default false). */
  readonly mobileOfflineRevisions: boolean;
  /** Phase 9: durable START_SERVER_PROCESSING ops (default false). */
  readonly mobileOfflineServerProcessing: boolean;
  /** Phase 9: backend idempotency helpers for offline replays (default false). */
  readonly serverOfflineIdempotencySupport: boolean;
}

/** Non-production defaults. Phase 1/2 upload optimizations default off in production. */
export const DEFAULT_FEATURE_FLAGS: FeatureFlags = {
  allowMobileDataUploads: true,
  heicConvertToJpeg: true,
  workManagerScheduling: false,
  advancedReconciliation: true,
  backgroundJobPolling: true,
  aisleDeviceLock: false,
  uploadObservabilityEnabled: true,
  captureFinishInstrumentation: true,
  captureFinishSafeMediaCheck: true,
  captureSessionFreeze: true,
  uploadIncrementalSnapshots: true,
  uploadPrepareParallelism: true,
  localCompletion: true,
  mobileCsvExport: true,
  serverCsvImport: false,
  localRemoteReconciliation: true,
  uploadDimensionCap: true,
  uploadAdaptiveQuality: true,
  uploadAdaptiveConcurrency: true,
  uploadAbortEnabled: true,
  backgroundUploadWorker: true,
  backgroundUploadForegroundService: true,
  backgroundUploadRebootResume: true,
  mobileLocalCodeScan: false,
  mobileLocalCodeScanShadowCompare: false,
  mobilePreliminaryDetectionSync: false,
  mobilePreliminaryReconciliationView: false,
  mobilePreliminaryReconciliationTrigger: false,
  mobileAuthoritativeLocalCodeScan: false,
  mobileLocalResultReview: false,
  mobileAuthoritativeAisleFinalization: false,
  authoritativeFinalizationOfflineQueue: false,
  mobileServerReprocess: false,
  mobileServerReprocessReview: false,
  serverReprocessOfflineQueue: false,
  mobileAisleRevisions: false,
  mobileAisleHistory: false,
  serverAisleRevisions: false,
  serverAisleRollback: false,
  mobileOfflineOperations: false,
  mobileOfflineWorkManager: false,
  mobileOfflineFinalization: false,
  mobileOfflineRevisions: false,
  mobileOfflineServerProcessing: false,
  serverOfflineIdempotencySupport: false,
};

function phaseOptInDefaultForEnvironment(environment: string): boolean {
  return environment !== 'production';
}

export function resolveFeatureFlags(raw: unknown, environment: string): FeatureFlags {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const optInDefault = phaseOptInDefaultForEnvironment(environment);
  const bool = (key: keyof FeatureFlags, fallback: boolean): boolean => {
    const v = source[key];
    if (typeof v === 'boolean') {
      return v;
    }
    if (v === 'true' || v === '1') {
      return true;
    }
    if (v === 'false' || v === '0') {
      return false;
    }
    return fallback;
  };
  return {
    allowMobileDataUploads: bool('allowMobileDataUploads', DEFAULT_FEATURE_FLAGS.allowMobileDataUploads),
    heicConvertToJpeg: bool('heicConvertToJpeg', DEFAULT_FEATURE_FLAGS.heicConvertToJpeg),
    workManagerScheduling: bool(
      'workManagerScheduling',
      DEFAULT_FEATURE_FLAGS.workManagerScheduling,
    ),
    advancedReconciliation: bool('advancedReconciliation', DEFAULT_FEATURE_FLAGS.advancedReconciliation),
    backgroundJobPolling: bool('backgroundJobPolling', DEFAULT_FEATURE_FLAGS.backgroundJobPolling),
    aisleDeviceLock: bool('aisleDeviceLock', false),
    uploadObservabilityEnabled: bool(
      'uploadObservabilityEnabled',
      DEFAULT_FEATURE_FLAGS.uploadObservabilityEnabled,
    ),
    captureFinishInstrumentation: bool(
      'captureFinishInstrumentation',
      DEFAULT_FEATURE_FLAGS.captureFinishInstrumentation,
    ),
    captureFinishSafeMediaCheck: bool(
      'captureFinishSafeMediaCheck',
      DEFAULT_FEATURE_FLAGS.captureFinishSafeMediaCheck,
    ),
    captureSessionFreeze: bool(
      'captureSessionFreeze',
      DEFAULT_FEATURE_FLAGS.captureSessionFreeze,
    ),
    uploadIncrementalSnapshots: bool(
      'uploadIncrementalSnapshots',
      DEFAULT_FEATURE_FLAGS.uploadIncrementalSnapshots,
    ),
    uploadPrepareParallelism: bool(
      'uploadPrepareParallelism',
      DEFAULT_FEATURE_FLAGS.uploadPrepareParallelism,
    ),
    localCompletion: bool('localCompletion', DEFAULT_FEATURE_FLAGS.localCompletion),
    mobileCsvExport: bool('mobileCsvExport', DEFAULT_FEATURE_FLAGS.mobileCsvExport),
    serverCsvImport: bool('serverCsvImport', DEFAULT_FEATURE_FLAGS.serverCsvImport),
    localRemoteReconciliation: bool(
      'localRemoteReconciliation',
      DEFAULT_FEATURE_FLAGS.localRemoteReconciliation,
    ),
    uploadDimensionCap: bool('uploadDimensionCap', optInDefault),
    uploadAdaptiveQuality: bool('uploadAdaptiveQuality', optInDefault),
    uploadAdaptiveConcurrency: bool('uploadAdaptiveConcurrency', optInDefault),
    uploadAbortEnabled: bool('uploadAbortEnabled', optInDefault),
    backgroundUploadWorker: bool('backgroundUploadWorker', optInDefault),
    backgroundUploadForegroundService: bool('backgroundUploadForegroundService', optInDefault),
    backgroundUploadRebootResume: bool('backgroundUploadRebootResume', optInDefault),
    // Phase 3: kill-switch defaults off in every environment until explicitly enabled.
    mobileLocalCodeScan: bool('mobileLocalCodeScan', false),
    mobileLocalCodeScanShadowCompare: bool('mobileLocalCodeScanShadowCompare', false),
    // Phase 4: preliminary sync — default off. JS scheduler only (no WorkManager worker).
    mobilePreliminaryDetectionSync: bool('mobilePreliminaryDetectionSync', false),
    mobilePreliminaryReconciliationView: bool('mobilePreliminaryReconciliationView', false),
    mobilePreliminaryReconciliationTrigger: bool(
      'mobilePreliminaryReconciliationTrigger',
      false,
    ),
    mobileAuthoritativeLocalCodeScan: bool('mobileAuthoritativeLocalCodeScan', false),
    mobileLocalResultReview: bool('mobileLocalResultReview', false),
    mobileAuthoritativeAisleFinalization: bool('mobileAuthoritativeAisleFinalization', false),
    authoritativeFinalizationOfflineQueue: bool(
      'authoritativeFinalizationOfflineQueue',
      false,
    ),
    mobileServerReprocess: bool('mobileServerReprocess', false),
    mobileServerReprocessReview: bool('mobileServerReprocessReview', false),
    serverReprocessOfflineQueue: bool('serverReprocessOfflineQueue', false),
    mobileAisleRevisions: bool('mobileAisleRevisions', false),
    mobileAisleHistory: bool('mobileAisleHistory', false),
    serverAisleRevisions: bool('serverAisleRevisions', false),
    serverAisleRollback: bool('serverAisleRollback', false),
    mobileOfflineOperations: bool('mobileOfflineOperations', false),
    mobileOfflineWorkManager: bool('mobileOfflineWorkManager', false),
    mobileOfflineFinalization: bool('mobileOfflineFinalization', false),
    mobileOfflineRevisions: bool('mobileOfflineRevisions', false),
    mobileOfflineServerProcessing: bool('mobileOfflineServerProcessing', false),
    serverOfflineIdempotencySupport: bool('serverOfflineIdempotencySupport', false),
  };
}
