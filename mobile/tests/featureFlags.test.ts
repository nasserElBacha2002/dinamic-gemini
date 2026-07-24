import { resolveFeatureFlags, DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';

describe('featureFlags', () => {
  it('uses defaults when raw is empty in development', () => {
    expect(resolveFeatureFlags(undefined, 'development')).toEqual(DEFAULT_FEATURE_FLAGS);
  });

  it('parses boolean and string flags', () => {
    const flags = resolveFeatureFlags(
      {
        allowMobileDataUploads: false,
        heicConvertToJpeg: '0',
        aisleDeviceLock: '1',
        uploadObservabilityEnabled: '0',
      },
      'staging',
    );
    expect(flags.allowMobileDataUploads).toBe(false);
    expect(flags.heicConvertToJpeg).toBe(false);
    expect(flags.aisleDeviceLock).toBe(true);
    expect(flags.uploadObservabilityEnabled).toBe(false);
  });

  it('keeps aisle lock off by default even in production', () => {
    expect(resolveFeatureFlags({}, 'production').aisleDeviceLock).toBe(false);
  });

  it('enables upload observability by default (kill switch via 0)', () => {
    expect(resolveFeatureFlags({}, 'production').uploadObservabilityEnabled).toBe(true);
  });

  it('keeps phase1 upload optimization flags on by default in development/staging', () => {
    for (const env of ['development', 'staging'] as const) {
      const flags = resolveFeatureFlags({}, env);
      expect(flags.uploadDimensionCap).toBe(true);
      expect(flags.uploadAdaptiveQuality).toBe(true);
      expect(flags.uploadAdaptiveConcurrency).toBe(true);
      expect(flags.uploadAbortEnabled).toBe(true);
    }
  });

  it('defaults phase1 flags off in production (opt-in until device validation)', () => {
    const flags = resolveFeatureFlags({}, 'production');
    expect(flags.uploadDimensionCap).toBe(false);
    expect(flags.uploadAdaptiveQuality).toBe(false);
    expect(flags.uploadAdaptiveConcurrency).toBe(false);
    expect(flags.uploadAbortEnabled).toBe(false);
  });

  it('can independently enable phase1 flags in production', () => {
    const flags = resolveFeatureFlags(
      {
        uploadDimensionCap: '1',
        uploadAdaptiveQuality: true,
        uploadAdaptiveConcurrency: '1',
        uploadAbortEnabled: '1',
      },
      'production',
    );
    expect(flags.uploadDimensionCap).toBe(true);
    expect(flags.uploadAdaptiveQuality).toBe(true);
    expect(flags.uploadAdaptiveConcurrency).toBe(true);
    expect(flags.uploadAbortEnabled).toBe(true);
  });

  it('defaults phase3 local code scan flags off in every environment', () => {
    for (const env of ['development', 'staging', 'production'] as const) {
      const flags = resolveFeatureFlags({}, env);
      expect(flags.mobileLocalCodeScan).toBe(false);
      expect(flags.mobileLocalCodeScanShadowCompare).toBe(false);
      expect(flags.mobilePreliminaryDetectionSync).toBe(false);
    }
  });

  it('can independently enable phase3 local code scan flags', () => {
    const flags = resolveFeatureFlags(
      {
        mobileLocalCodeScan: '1',
        mobileLocalCodeScanShadowCompare: true,
      },
      'production',
    );
    expect(flags.mobileLocalCodeScan).toBe(true);
    expect(flags.mobileLocalCodeScanShadowCompare).toBe(true);
  });

  it('can independently enable phase4 preliminary sync flags', () => {
    const flags = resolveFeatureFlags(
      {
        mobilePreliminaryDetectionSync: '1',
      },
      'production',
    );
    expect(flags.mobilePreliminaryDetectionSync).toBe(true);
  });

  it('defaults phase5 reconciliation view flag off', () => {
    for (const env of ['development', 'staging', 'production'] as const) {
      expect(resolveFeatureFlags({}, env).mobilePreliminaryReconciliationView).toBe(false);
      expect(resolveFeatureFlags({}, env).mobilePreliminaryReconciliationTrigger).toBe(false);
      expect(resolveFeatureFlags({}, env).mobileAuthoritativeLocalCodeScan).toBe(false);
      expect(resolveFeatureFlags({}, env).mobileLocalResultReview).toBe(false);
    }
    const on = resolveFeatureFlags(
      {
        mobilePreliminaryReconciliationView: '1',
        mobilePreliminaryReconciliationTrigger: '1',
      },
      'production',
    );
    expect(on.mobilePreliminaryReconciliationView).toBe(true);
    expect(on.mobilePreliminaryReconciliationTrigger).toBe(true);
  });

  it('can independently enable authoritative local result flags', () => {
    const on = resolveFeatureFlags(
      {
        mobileAuthoritativeLocalCodeScan: '1',
        mobileLocalResultReview: true,
      },
      'production',
    );
    expect(on.mobileAuthoritativeLocalCodeScan).toBe(true);
    expect(on.mobileLocalResultReview).toBe(true);
  });
});
