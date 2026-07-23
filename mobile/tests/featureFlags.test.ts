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

  it('can independently disable phase1 flags in development', () => {
    const flags = resolveFeatureFlags(
      {
        uploadDimensionCap: '0',
        uploadAdaptiveQuality: false,
        uploadAdaptiveConcurrency: '0',
        uploadAbortEnabled: '0',
        heicConvertToJpeg: '0',
      },
      'development',
    );
    expect(flags.uploadDimensionCap).toBe(false);
    expect(flags.uploadAdaptiveQuality).toBe(false);
    expect(flags.uploadAdaptiveConcurrency).toBe(false);
    expect(flags.uploadAbortEnabled).toBe(false);
    expect(flags.heicConvertToJpeg).toBe(false);
  });
});
