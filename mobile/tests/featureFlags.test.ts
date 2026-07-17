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
      },
      'staging',
    );
    expect(flags.allowMobileDataUploads).toBe(false);
    expect(flags.heicConvertToJpeg).toBe(false);
    expect(flags.aisleDeviceLock).toBe(true);
  });

  it('keeps aisle lock off by default even in production', () => {
    expect(resolveFeatureFlags({}, 'production').aisleDeviceLock).toBe(false);
  });
});
