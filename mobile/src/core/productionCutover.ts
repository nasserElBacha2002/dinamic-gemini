/**
 * Phase 10 — configurable cutover / pause thresholds (no hardcoded ops SLOs).
 * Values come from Expo `extra.cutover` or process.env in tests/CI.
 */

export interface ProductionCutoverThresholds {
  /** Minimum success rate (0–1) to continue rollout. */
  readonly minSuccessRate: number;
  /** Maximum error rate (0–1) before auto-pause. */
  readonly maxErrorRate: number;
  /** Maximum duplicate job rate (0–1); prefer 0. */
  readonly maxDuplicateRate: number;
  /** Maximum stale conflict rate (0–1). */
  readonly maxStaleRate: number;
  /** Minimum recovery success rate (0–1). */
  readonly minRecoverySuccessRate: number;
  /** Maximum crash rate (0–1) for mobile releases. */
  readonly maxCrashRate: number;
  /** p95 duration ceiling in ms for aisle finalize (0 = disabled). */
  readonly maxP95FinalizationMs: number;
  /** Queue depth warning / critical. */
  readonly queueDepthWarning: number;
  readonly queueDepthCritical: number;
  /** Oldest pending age seconds warning / critical. */
  readonly oldestPendingAgeWarningSec: number;
  readonly oldestPendingAgeCriticalSec: number;
}

export const DEFAULT_PRODUCTION_CUTOVER: ProductionCutoverThresholds = {
  minSuccessRate: 0.99,
  maxErrorRate: 0.01,
  maxDuplicateRate: 0,
  maxStaleRate: 0.02,
  minRecoverySuccessRate: 0.99,
  maxCrashRate: 0.005,
  maxP95FinalizationMs: 0,
  queueDepthWarning: 100,
  queueDepthCritical: 500,
  oldestPendingAgeWarningSec: 900,
  oldestPendingAgeCriticalSec: 3600,
};

function asFiniteNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return n;
    }
  }
  return fallback;
}

function fromEnv(name: string): string {
  return typeof process !== 'undefined' && process.env?.[name] ? String(process.env[name]).trim() : '';
}

/** Resolve cutover thresholds from optional raw config + env overrides. */
export function resolveProductionCutover(raw: unknown): ProductionCutoverThresholds {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const num = (key: keyof ProductionCutoverThresholds, envKey: string, fallback: number): number => {
    const envVal = fromEnv(envKey);
    if (envVal) {
      return asFiniteNumber(envVal, fallback);
    }
    return asFiniteNumber(source[key], fallback);
  };
  return {
    minSuccessRate: num('minSuccessRate', 'DINAMIC_CUTOVER_MIN_SUCCESS_RATE', DEFAULT_PRODUCTION_CUTOVER.minSuccessRate),
    maxErrorRate: num('maxErrorRate', 'DINAMIC_CUTOVER_MAX_ERROR_RATE', DEFAULT_PRODUCTION_CUTOVER.maxErrorRate),
    maxDuplicateRate: num(
      'maxDuplicateRate',
      'DINAMIC_CUTOVER_MAX_DUPLICATE_RATE',
      DEFAULT_PRODUCTION_CUTOVER.maxDuplicateRate,
    ),
    maxStaleRate: num('maxStaleRate', 'DINAMIC_CUTOVER_MAX_STALE_RATE', DEFAULT_PRODUCTION_CUTOVER.maxStaleRate),
    minRecoverySuccessRate: num(
      'minRecoverySuccessRate',
      'DINAMIC_CUTOVER_MIN_RECOVERY_SUCCESS_RATE',
      DEFAULT_PRODUCTION_CUTOVER.minRecoverySuccessRate,
    ),
    maxCrashRate: num('maxCrashRate', 'DINAMIC_CUTOVER_MAX_CRASH_RATE', DEFAULT_PRODUCTION_CUTOVER.maxCrashRate),
    maxP95FinalizationMs: num(
      'maxP95FinalizationMs',
      'DINAMIC_CUTOVER_MAX_P95_FINALIZATION_MS',
      DEFAULT_PRODUCTION_CUTOVER.maxP95FinalizationMs,
    ),
    queueDepthWarning: num(
      'queueDepthWarning',
      'DINAMIC_ALERT_QUEUE_DEPTH_WARNING',
      DEFAULT_PRODUCTION_CUTOVER.queueDepthWarning,
    ),
    queueDepthCritical: num(
      'queueDepthCritical',
      'DINAMIC_ALERT_QUEUE_DEPTH_CRITICAL',
      DEFAULT_PRODUCTION_CUTOVER.queueDepthCritical,
    ),
    oldestPendingAgeWarningSec: num(
      'oldestPendingAgeWarningSec',
      'DINAMIC_ALERT_OLDEST_PENDING_WARNING_SEC',
      DEFAULT_PRODUCTION_CUTOVER.oldestPendingAgeWarningSec,
    ),
    oldestPendingAgeCriticalSec: num(
      'oldestPendingAgeCriticalSec',
      'DINAMIC_ALERT_OLDEST_PENDING_CRITICAL_SEC',
      DEFAULT_PRODUCTION_CUTOVER.oldestPendingAgeCriticalSec,
    ),
  };
}

export interface RolloutPauseSignals {
  readonly successRate: number;
  readonly errorRate: number;
  readonly duplicateRate: number;
  readonly staleRate: number;
  readonly recoverySuccessRate: number;
  readonly crashRate: number;
  readonly p95FinalizationMs?: number;
  readonly queueDepth?: number;
  readonly oldestPendingAgeSec?: number;
}

export type RolloutDecision = 'continue' | 'pause_warning' | 'pause_critical';

/** Evaluate whether rollout should auto-pause given live signals vs thresholds. */
export function evaluateRolloutPause(
  thresholds: ProductionCutoverThresholds,
  signals: RolloutPauseSignals,
): { readonly decision: RolloutDecision; readonly reasons: readonly string[] } {
  const reasons: string[] = [];
  let decision: RolloutDecision = 'continue';

  const bump = (level: RolloutDecision, reason: string) => {
    reasons.push(reason);
    if (level === 'pause_critical') {
      decision = 'pause_critical';
      return;
    }
    if (decision === 'continue') {
      decision = level;
    }
  };

  if (signals.successRate < thresholds.minSuccessRate) {
    bump('pause_critical', `successRate ${signals.successRate} < ${thresholds.minSuccessRate}`);
  }
  if (signals.errorRate > thresholds.maxErrorRate) {
    bump('pause_critical', `errorRate ${signals.errorRate} > ${thresholds.maxErrorRate}`);
  }
  if (signals.duplicateRate > thresholds.maxDuplicateRate) {
    bump('pause_critical', `duplicateRate ${signals.duplicateRate} > ${thresholds.maxDuplicateRate}`);
  }
  if (signals.staleRate > thresholds.maxStaleRate) {
    bump('pause_warning', `staleRate ${signals.staleRate} > ${thresholds.maxStaleRate}`);
  }
  if (signals.recoverySuccessRate < thresholds.minRecoverySuccessRate) {
    bump('pause_critical', `recoverySuccessRate ${signals.recoverySuccessRate} < ${thresholds.minRecoverySuccessRate}`);
  }
  if (signals.crashRate > thresholds.maxCrashRate) {
    bump('pause_critical', `crashRate ${signals.crashRate} > ${thresholds.maxCrashRate}`);
  }
  if (
    thresholds.maxP95FinalizationMs > 0 &&
    typeof signals.p95FinalizationMs === 'number' &&
    signals.p95FinalizationMs > thresholds.maxP95FinalizationMs
  ) {
    bump('pause_warning', `p95FinalizationMs ${signals.p95FinalizationMs} > ${thresholds.maxP95FinalizationMs}`);
  }
  if (typeof signals.queueDepth === 'number') {
    if (signals.queueDepth >= thresholds.queueDepthCritical) {
      bump('pause_critical', `queueDepth ${signals.queueDepth} >= ${thresholds.queueDepthCritical}`);
    } else if (signals.queueDepth >= thresholds.queueDepthWarning) {
      bump('pause_warning', `queueDepth ${signals.queueDepth} >= ${thresholds.queueDepthWarning}`);
    }
  }
  if (typeof signals.oldestPendingAgeSec === 'number') {
    if (signals.oldestPendingAgeSec >= thresholds.oldestPendingAgeCriticalSec) {
      bump(
        'pause_critical',
        `oldestPendingAgeSec ${signals.oldestPendingAgeSec} >= ${thresholds.oldestPendingAgeCriticalSec}`,
      );
    } else if (signals.oldestPendingAgeSec >= thresholds.oldestPendingAgeWarningSec) {
      bump(
        'pause_warning',
        `oldestPendingAgeSec ${signals.oldestPendingAgeSec} >= ${thresholds.oldestPendingAgeWarningSec}`,
      );
    }
  }

  return { decision, reasons };
}
