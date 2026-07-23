export interface FeatureFlags {
  readonly allowMobileDataUploads: boolean;
  /**
   * When true (default), convert HEIC/HEIF to JPEG before upload.
   * When false, upload HEIC as-is (backend worker can normalize).
   */
  readonly heicConvertToJpeg: boolean;
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
}

/** Non-production defaults (development / staging). Production Phase 1 flags default off (opt-in). */
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
};

function phase1DefaultForEnvironment(environment: string): boolean {
  return environment !== 'production';
}

export function resolveFeatureFlags(raw: unknown, environment: string): FeatureFlags {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const phase1Default = phase1DefaultForEnvironment(environment);
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
    uploadDimensionCap: bool('uploadDimensionCap', phase1Default),
    uploadAdaptiveQuality: bool('uploadAdaptiveQuality', phase1Default),
    uploadAdaptiveConcurrency: bool('uploadAdaptiveConcurrency', phase1Default),
    uploadAbortEnabled: bool('uploadAbortEnabled', phase1Default),
  };
}
