/**
 * Centralized policy: when originals may be read for ZIP packaging (Phase 4).
 * No silent fallback — callers must pass through this decision.
 */

import type { CaptureSessionRow } from '../../database/schema/captureSchema';
import { classifySessionExportPolicy } from './sessionExportPolicy';

export type OriginalFallbackReason =
  | 'FEATURE_DISABLED'
  | 'LEGACY_SESSION_WITHOUT_PREP'
  | 'EXPLICIT_RECOVERY_POLICY';

export type ExportSourceMode = 'staging_required' | 'legacy_originals';

export interface ExportSourcePolicyDecision {
  readonly mode: ExportSourceMode;
  /** Set only when mode === 'legacy_originals'. */
  readonly fallbackReason: OriginalFallbackReason | null;
}

/**
 * Decide packaging source for a session.
 *
 * Prefer classifySessionExportPolicy when a session row is available so legacy
 * is never inferred solely from freezeId == null.
 */
export function decideExportSourcePolicy(input: {
  readonly exportPrepEnabled: boolean;
  readonly session?: CaptureSessionRow | null;
  /** Reserved: when true, allow controlled original reads (must be intentional). */
  readonly allowExplicitRecoveryFallback?: boolean;
}): ExportSourcePolicyDecision {
  if (input.allowExplicitRecoveryFallback === true) {
    return {
      mode: 'legacy_originals',
      fallbackReason: 'EXPLICIT_RECOVERY_POLICY',
    };
  }
  if (input.session) {
    const c = classifySessionExportPolicy(input.session, input.exportPrepEnabled);
    if (c.packagingMode === 'LEGACY_ORIGINALS' || !input.exportPrepEnabled) {
      return {
        mode: 'legacy_originals',
        fallbackReason: c.fallbackReason ?? 'FEATURE_DISABLED',
      };
    }
    return { mode: 'staging_required', fallbackReason: null };
  }
  if (input.exportPrepEnabled !== true) {
    return { mode: 'legacy_originals', fallbackReason: 'FEATURE_DISABLED' };
  }
  return { mode: 'staging_required', fallbackReason: null };
}
