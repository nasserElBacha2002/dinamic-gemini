import { DEFAULT_FEATURE_FLAGS, resolveFeatureFlags } from '../src/core/featureFlags';
import {
  evaluateFeatureFlagCompatibility,
  formatFlagCompatibilityErrors,
} from '../src/core/featureFlagCompatibility';
import { resolveAppConfig, validateAppConfig } from '../src/runtime/config/resolveAppConfig';
import {
  DEFAULT_PRODUCTION_CUTOVER,
  evaluateRolloutPause,
  resolveProductionCutover,
} from '../src/core/productionCutover';

describe('featureFlagCompatibility', () => {
  it('allows default flags', () => {
    const report = evaluateFeatureFlagCompatibility(DEFAULT_FEATURE_FLAGS);
    expect(report.hasErrors).toBe(false);
    expect(formatFlagCompatibilityErrors(report)).toBeNull();
  });

  it('rejects WorkManager without offline ledger', () => {
    const flags = resolveFeatureFlags(
      { mobileOfflineWorkManager: true, mobileOfflineOperations: false },
      'development',
    );
    const report = evaluateFeatureFlagCompatibility(flags);
    expect(report.hasErrors).toBe(true);
    expect(report.issues.some((i) => i.code === 'OFFLINE_WM_WITHOUT_LEDGER')).toBe(true);
  });

  it('rejects dual finalization queues', () => {
    const flags = resolveFeatureFlags(
      {
        mobileOfflineOperations: true,
        mobileOfflineFinalization: true,
        authoritativeFinalizationOfflineQueue: true,
      },
      'development',
    );
    const report = evaluateFeatureFlagCompatibility(flags);
    expect(report.issues.some((i) => i.code === 'LEGACY_FINALIZATION_QUEUE_WITH_LEDGER')).toBe(
      true,
    );
  });

  it('fails validateAppConfig when production uses HTTP', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'http://api.example.com',
      environment: 'production',
    });
    const err = validateAppConfig(config);
    expect(err).toContain('HTTPS');
  });

  it('fails validateAppConfig on incompatible flags', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'https://api.example.com',
      environment: 'production',
      flags: { mobileOfflineWorkManager: true, mobileOfflineOperations: false },
    });
    const err = validateAppConfig(config);
    expect(err).toContain('OFFLINE_WM_WITHOUT_LEDGER');
    expect(err).not.toContain('HTTPS');
  });

  it('warns when preliminary + authoritative are both on', () => {
    const flags = resolveFeatureFlags(
      {
        mobilePreliminaryDetectionSync: true,
        mobileAuthoritativeLocalCodeScan: true,
      },
      'development',
    );
    const report = evaluateFeatureFlagCompatibility(flags);
    expect(report.hasErrors).toBe(false);
    expect(report.hasWarnings).toBe(true);
    expect(report.issues.some((i) => i.code === 'PRELIMINARY_WITH_AUTHORITATIVE')).toBe(true);
  });
});

describe('productionCutover', () => {
  it('resolves defaults', () => {
    expect(resolveProductionCutover(undefined)).toEqual(DEFAULT_PRODUCTION_CUTOVER);
  });

  it('pauses rollout on low success rate', () => {
    const result = evaluateRolloutPause(DEFAULT_PRODUCTION_CUTOVER, {
      successRate: 0.9,
      errorRate: 0,
      duplicateRate: 0,
      staleRate: 0,
      recoverySuccessRate: 1,
      crashRate: 0,
    });
    expect(result.decision).toBe('pause_critical');
    expect(result.reasons.length).toBeGreaterThan(0);
  });

  it('includes cutover on AppConfig', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'https://api.example.com',
      cutover: { queueDepthWarning: 42 },
    });
    expect(config.cutover.queueDepthWarning).toBe(42);
    expect(config.cutover.minSuccessRate).toBe(DEFAULT_PRODUCTION_CUTOVER.minSuccessRate);
  });
});
