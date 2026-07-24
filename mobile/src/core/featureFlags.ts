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
  uploadDimensionCap: true,
  uploadAdaptiveQuality: true,
  uploadAdaptiveConcurrency: true,
  uploadAbortEnabled: true,
  backgroundUploadWorker: true,
  backgroundUploadForegroundService: true,
  backgroundUploadRebootResume: true,
  mobileLocalCodeScan: false,
  mobileLocalCodeScanShadowCompare: false,
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
  };
}
