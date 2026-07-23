import { resolveFeatureFlags, DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';

describe('featureFlags', () => {
  it('uses defaults when raw is empty', () => {
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

  it('enables phase1 upload optimization flags by default', () => {
    const flags = resolveFeatureFlags({}, 'production');
    expect(flags.uploadDimensionCap).toBe(true);
    expect(flags.uploadAdaptiveQuality).toBe(true);
    expect(flags.uploadAdaptiveConcurrency).toBe(true);
    expect(flags.uploadAbortEnabled).toBe(true);
  });

  it('can independently disable phase1 flags', () => {
    const flags = resolveFeatureFlags(
      {
        uploadDimensionCap: '0',
        uploadAdaptiveQuality: false,
        uploadAdaptiveConcurrency: '0',
        uploadAbortEnabled: '0',
        heicConvertToJpeg: '0',
      },
      'production',
    );
    expect(flags.uploadDimensionCap).toBe(false);
    expect(flags.uploadAdaptiveQuality).toBe(false);
    expect(flags.uploadAdaptiveConcurrency).toBe(false);
    expect(flags.uploadAbortEnabled).toBe(false);
    expect(flags.heicConvertToJpeg).toBe(false);
  });
});
