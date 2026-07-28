import type { FeatureFlags } from './featureFlags';

export type FlagCompatibilitySeverity = 'error' | 'warning';

export interface FlagCompatibilityIssue {
  readonly code: string;
  readonly severity: FlagCompatibilitySeverity;
  readonly message: string;
  readonly flags: readonly (keyof FeatureFlags)[];
}

export interface FlagCompatibilityReport {
  readonly issues: readonly FlagCompatibilityIssue[];
  readonly hasErrors: boolean;
  readonly hasWarnings: boolean;
}

/**
 * Phase 10 — fail-fast matrix for incompatible / dangerous flag combinations.
 * Dual productive schedulers for the same work class are hard errors.
 */
export function evaluateFeatureFlagCompatibility(flags: FeatureFlags): FlagCompatibilityReport {
  const issues: FlagCompatibilityIssue[] = [];

  if (flags.mobileOfflineWorkManager && !flags.mobileOfflineOperations) {
    issues.push({
      code: 'OFFLINE_WM_WITHOUT_LEDGER',
      severity: 'error',
      message:
        'mobileOfflineWorkManager requiere mobileOfflineOperations (WorkManager sin ledger es no-op peligroso).',
      flags: ['mobileOfflineWorkManager', 'mobileOfflineOperations'],
    });
  }

  if (flags.mobileOfflineFinalization && !flags.mobileOfflineOperations) {
    issues.push({
      code: 'OFFLINE_FINALIZATION_WITHOUT_LEDGER',
      severity: 'error',
      message: 'mobileOfflineFinalization requiere mobileOfflineOperations.',
      flags: ['mobileOfflineFinalization', 'mobileOfflineOperations'],
    });
  }

  if (flags.mobileOfflineRevisions && !flags.mobileOfflineOperations) {
    issues.push({
      code: 'OFFLINE_REVISIONS_WITHOUT_LEDGER',
      severity: 'error',
      message: 'mobileOfflineRevisions requiere mobileOfflineOperations.',
      flags: ['mobileOfflineRevisions', 'mobileOfflineOperations'],
    });
  }

  if (flags.mobileOfflineServerProcessing && !flags.mobileOfflineOperations) {
    issues.push({
      code: 'OFFLINE_SERVER_PROC_WITHOUT_LEDGER',
      severity: 'error',
      message: 'mobileOfflineServerProcessing requiere mobileOfflineOperations.',
      flags: ['mobileOfflineServerProcessing', 'mobileOfflineOperations'],
    });
  }

  // Dual durable offline queues for the same concern (legacy intent tables + Phase 9 ledger).
  if (
    flags.mobileOfflineOperations &&
    flags.authoritativeFinalizationOfflineQueue &&
    !flags.mobileOfflineFinalization
  ) {
    issues.push({
      code: 'DUAL_FINALIZATION_QUEUES',
      severity: 'error',
      message:
        'mobileOfflineOperations + authoritativeFinalizationOfflineQueue sin mobileOfflineFinalization ejecuta dos colas de finalización.',
      flags: [
        'mobileOfflineOperations',
        'authoritativeFinalizationOfflineQueue',
        'mobileOfflineFinalization',
      ],
    });
  }

  if (
    flags.mobileOfflineOperations &&
    flags.serverReprocessOfflineQueue &&
    !flags.mobileOfflineServerProcessing
  ) {
    issues.push({
      code: 'DUAL_REPROCESS_QUEUES',
      severity: 'error',
      message:
        'mobileOfflineOperations + serverReprocessOfflineQueue sin mobileOfflineServerProcessing ejecuta dos colas de reprocess.',
      flags: [
        'mobileOfflineOperations',
        'serverReprocessOfflineQueue',
        'mobileOfflineServerProcessing',
      ],
    });
  }

  if (flags.mobileOfflineFinalization && flags.authoritativeFinalizationOfflineQueue) {
    issues.push({
      code: 'LEGACY_FINALIZATION_QUEUE_WITH_LEDGER',
      severity: 'error',
      message:
        'No combinar authoritativeFinalizationOfflineQueue con mobileOfflineFinalization (dos schedulers).',
      flags: ['authoritativeFinalizationOfflineQueue', 'mobileOfflineFinalization'],
    });
  }

  if (flags.mobileOfflineServerProcessing && flags.serverReprocessOfflineQueue) {
    issues.push({
      code: 'LEGACY_REPROCESS_QUEUE_WITH_LEDGER',
      severity: 'error',
      message:
        'No combinar serverReprocessOfflineQueue con mobileOfflineServerProcessing (dos schedulers).',
      flags: ['serverReprocessOfflineQueue', 'mobileOfflineServerProcessing'],
    });
  }

  if (flags.mobilePreliminaryDetectionSync && flags.mobileAuthoritativeLocalCodeScan) {
    issues.push({
      code: 'PRELIMINARY_WITH_AUTHORITATIVE',
      severity: 'warning',
      message:
        'preliminary sync + authoritative local CODE_SCAN: preliminary es diagnóstico deprecated; preferir solo authoritative en producción.',
      flags: ['mobilePreliminaryDetectionSync', 'mobileAuthoritativeLocalCodeScan'],
    });
  }

  if (flags.mobileLocalCodeScanShadowCompare && !flags.mobileLocalCodeScan) {
    issues.push({
      code: 'SHADOW_WITHOUT_LOCAL_SCAN',
      severity: 'error',
      message: 'mobileLocalCodeScanShadowCompare requiere mobileLocalCodeScan.',
      flags: ['mobileLocalCodeScanShadowCompare', 'mobileLocalCodeScan'],
    });
  }

  if (flags.mobileServerReprocessReview && !flags.mobileServerReprocess) {
    issues.push({
      code: 'REPROCESS_REVIEW_WITHOUT_REPROCESS',
      severity: 'warning',
      message: 'mobileServerReprocessReview sin mobileServerReprocess no tiene efecto útil.',
      flags: ['mobileServerReprocessReview', 'mobileServerReprocess'],
    });
  }

  if (flags.serverAisleRollback && !flags.serverAisleRevisions) {
    issues.push({
      code: 'ROLLBACK_WITHOUT_REVISIONS',
      severity: 'error',
      message: 'serverAisleRollback requiere serverAisleRevisions.',
      flags: ['serverAisleRollback', 'serverAisleRevisions'],
    });
  }

  if (flags.mobileAisleHistory && !flags.mobileAisleRevisions) {
    issues.push({
      code: 'HISTORY_WITHOUT_REVISIONS',
      severity: 'warning',
      message: 'mobileAisleHistory sin mobileAisleRevisions es UI incompleta.',
      flags: ['mobileAisleHistory', 'mobileAisleRevisions'],
    });
  }

  return {
    issues,
    hasErrors: issues.some((i) => i.severity === 'error'),
    hasWarnings: issues.some((i) => i.severity === 'warning'),
  };
}

/** Hard-fail message for bootstrap / validateAppConfig (errors only). */
export function formatFlagCompatibilityErrors(report: FlagCompatibilityReport): string | null {
  const errors = report.issues.filter((i) => i.severity === 'error');
  if (errors.length === 0) {
    return null;
  }
  return errors.map((e) => `[${e.code}] ${e.message}`).join(' ');
}
