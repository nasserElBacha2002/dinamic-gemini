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
  /** upload/process observability (kill switch: set DINAMIC_FLAG_UPLOAD_OBS=0). */
  readonly uploadObservabilityEnabled: boolean;
  /** emit capture.finish_* stage events (safe; default on). */
  readonly captureFinishInstrumentation: boolean;
  /** light MediaStore check before skipping finish rescan (default on). */
  readonly captureFinishSafeMediaCheck: boolean;
  /** persist capture freeze watermark on finish (default on). */
  readonly captureSessionFreeze: boolean;
  /** debounce UploadQueue emit/refreshCachedSessions (default on). */
  readonly uploadIncrementalSnapshots: boolean;
  /** network-aware prepare parallelism (default on). */
  readonly uploadPrepareParallelism: boolean;
  /** allow closing capture locally without upload/process (default on). */
  readonly localCompletion: boolean;
  /** offline local CSV export (default on). */
  readonly mobileCsvExport: boolean;
  /**
   * When false (default), server photo/result upload and processing flows are disabled.
   * Capture → review → local save → ZIP export only.
   */
  readonly mobileServerUpload: boolean;
  /** client may call server CSV import APIs (default false until server flag on). */
  readonly serverCsvImport: boolean;
  /** classify local vs server result conflicts (default on). */
  readonly localRemoteReconciliation: boolean;
  /** proactive max-edge dimension cap during prepare. */
  readonly uploadDimensionCap: boolean;
  /** profile/network JPEG quality instead of legacy fixed qualities. */
  readonly uploadAdaptiveQuality: boolean;
  /** network-aware upload concurrency (still capped). */
  readonly uploadAdaptiveConcurrency: boolean;
  /** abort in-flight multipart when cancelPhoto runs. */
  readonly uploadAbortEnabled: boolean;
  /** native WorkManager upload worker. */
  readonly backgroundUploadWorker: boolean;
  /** promote long uploads to Foreground Service notification. */
  readonly backgroundUploadForegroundService: boolean;
  /** allow WorkManager to resume after device reboot. */
  readonly backgroundUploadRebootResume: boolean;
  /** local CODE_SCAN shadow detection (hard opt-in; default false). */
  readonly mobileLocalCodeScan: boolean;
  /** attempt shadow compare when a reliable mapping exists. */
  readonly mobileLocalCodeScanShadowCompare: boolean;
  /** sync local drafts to server as diagnostic evidence (default false). */
  readonly mobilePreliminaryDetectionSync: boolean;
  /** show server reconciliation outcomes (default false). */
  readonly mobilePreliminaryReconciliationView: boolean;
  /** allow JobMonitor to trigger server reconcile enqueue (default false). */
  readonly mobilePreliminaryReconciliationTrigger: boolean;
  /** Authoritative local CODE_SCAN: operator-confirmed results sync (default false). */
  readonly mobileAuthoritativeLocalCodeScan: boolean;
  /** Authoritative local CODE_SCAN: review screen before upload (default false). */
  readonly mobileLocalResultReview: boolean;
  /** authoritative aisle finalization without remote reprocess (default false). */
  readonly mobileAuthoritativeAisleFinalization: boolean;
  /** persist offline finalization intent (default false). */
  readonly authoritativeFinalizationOfflineQueue: boolean;
  /** optional server reprocess action (default false). */
  readonly mobileServerReprocess: boolean;
  /** proposal review / adoption UI (default false). */
  readonly mobileServerReprocessReview: boolean;
  /** persist offline reprocess request intent (default false). */
  readonly serverReprocessOfflineQueue: boolean;
  /** mobile aisle correction / revision UX (default false). */
  readonly mobileAisleRevisions: boolean;
  /** mobile aisle revision history screen (default false). */
  readonly mobileAisleHistory: boolean;
  /** call server aisle revision APIs (default false). */
  readonly serverAisleRevisions: boolean;
  /** allow rollback from history (default false). */
  readonly serverAisleRollback: boolean;
  /** unified durable offline_operations ledger + scheduler (default false). */
  readonly mobileOfflineOperations: boolean;
  /** schedule WorkManager wake for offline recovery (default false). */
  readonly mobileOfflineWorkManager: boolean;
  /** route finalization intents through offline_operations (default false). */
  readonly mobileOfflineFinalization: boolean;
  /** route revision sync/apply through offline_operations (default false). */
  readonly mobileOfflineRevisions: boolean;
  /** durable START_SERVER_PROCESSING ops (default false). */
  readonly mobileOfflineServerProcessing: boolean;
  /** backend idempotency helpers for offline replays (default false). */
  readonly serverOfflineIdempotencySupport: boolean;
  /** Canonical active position persistence V2 (rollout off by default). */
  readonly mobileCanonicalPositionStateEnabled: boolean;
  /** Restore active position from capture_sessions (rollout off by default). */
  readonly positionActiveStateRestoreEnabled: boolean;
  /** Add PositionSyncReference V2 to preliminary evidence. */
  readonly positionSyncReferenceV2Enabled: boolean;
  /**
   * Incremental export prep queue: stage originals + CODE_SCAN per stable photo
   * before ZIP packing. Kill-switch via DINAMIC_FLAG_EXPORT_PREP_QUEUE=0.
   * Default: on in non-production (opt-in style), off in production until device evidence.
   */
  readonly mobileExportPrepQueue: boolean;
}

/** Non-production defaults. upload optimizations default off in production. */
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
  mobileServerUpload: true,
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
  mobileCanonicalPositionStateEnabled: false,
  positionActiveStateRestoreEnabled: false,
  positionSyncReferenceV2Enabled: false,
  mobileExportPrepQueue: true,
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
    mobileServerUpload: bool('mobileServerUpload', DEFAULT_FEATURE_FLAGS.mobileServerUpload),
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
 // kill-switch defaults off in every environment until explicitly enabled.
    mobileLocalCodeScan: bool('mobileLocalCodeScan', false),
    mobileLocalCodeScanShadowCompare: bool('mobileLocalCodeScanShadowCompare', false),
 // preliminary sync — default off. JS scheduler only (no WorkManager worker).
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
    mobileCanonicalPositionStateEnabled: bool('mobileCanonicalPositionStateEnabled', false),
    positionActiveStateRestoreEnabled: bool('positionActiveStateRestoreEnabled', false),
    positionSyncReferenceV2Enabled: bool('positionSyncReferenceV2Enabled', false),
    mobileExportPrepQueue: bool('mobileExportPrepQueue', optInDefault),
  };
}
