import type { AppEnvironment } from '../../runtime/config/resolveAppConfig';

export type BenchmarkGateReason =
  | 'OK'
  | 'RELEASE_BLOCKED'
  | 'FLAG_REQUIRED'
  | 'EXCLUSIVE_SESSION_ACTIVE'
  | 'INVALID_COMMAND';

/**
 * Benchmark is debug/internal only. Production environment always blocks.
 * Requires explicit `enabled: true` in the command payload (not a silent default).
 */
export function evaluateBenchmarkGate(input: {
  readonly environment: AppEnvironment;
  readonly isDevelopment: boolean;
  readonly commandEnabled: boolean;
  readonly exclusiveSessionActive: boolean;
}): { readonly ok: boolean; readonly reason: BenchmarkGateReason } {
  if (input.environment === 'production' || !input.isDevelopment) {
    return { ok: false, reason: 'RELEASE_BLOCKED' };
  }
  if (!input.commandEnabled) {
    return { ok: false, reason: 'FLAG_REQUIRED' };
  }
  if (input.exclusiveSessionActive) {
    return { ok: false, reason: 'EXCLUSIVE_SESSION_ACTIVE' };
  }
  return { ok: true, reason: 'OK' };
}
