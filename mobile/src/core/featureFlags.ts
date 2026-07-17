export interface FeatureFlags {
  readonly allowMobileDataUploads: boolean;
  readonly heicConvertToJpeg: boolean;
  readonly workManagerScheduling: boolean;
  readonly advancedReconciliation: boolean;
  readonly backgroundJobPolling: boolean;
  readonly aisleDeviceLock: boolean;
}

export const DEFAULT_FEATURE_FLAGS: FeatureFlags = {
  allowMobileDataUploads: true,
  heicConvertToJpeg: true,
  workManagerScheduling: false,
  advancedReconciliation: true,
  backgroundJobPolling: true,
  aisleDeviceLock: false,
};

export function resolveFeatureFlags(raw: unknown, _environment: string): FeatureFlags {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
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
  };
}
