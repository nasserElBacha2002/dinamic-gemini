/**
 * Classify whether a session may export/drain without freeze (Phase 4 corrections).
 * Never infer legacy solely from freezeId == null.
 */

import type { CaptureSessionRow } from '../../database/schema/captureSchema';
import type { OriginalFallbackReason } from './exportSourcePolicy';

export type ExportPackagingMode = 'STAGING_REQUIRED' | 'LEGACY_ORIGINALS';

export interface SessionExportClassification {
  readonly packagingMode: ExportPackagingMode | null;
  /** When true, drain may proceed without freeze (historical / flag-off path). */
  readonly allowLegacyWithoutFreeze: boolean;
  readonly fallbackReason: OriginalFallbackReason | null;
  /** When true and freeze is null → FREEZE_MISSING. */
  readonly freezeRequired: boolean;
  /**
   * After commit to review with STAGING_REQUIRED, barrier is complete by construction
   * (finish waited producers and freeze is immutable).
   */
  readonly producerBarrierCompletedForRecovery: boolean;
}

function persistedMode(session: CaptureSessionRow): ExportPackagingMode | null {
  const raw = session.export_packaging_mode;
  if (raw === 'STAGING_REQUIRED' || raw === 'LEGACY_ORIGINALS') return raw;
  return null;
}

/**
 * Authoritative classification for drain/export.
 * Prep flag off → FEATURE_DISABLED (legacy originals for ZIP; drain may allowLegacy).
 */
export function classifySessionExportPolicy(
  session: CaptureSessionRow,
  exportPrepEnabled: boolean,
): SessionExportClassification {
  if (!exportPrepEnabled) {
    return {
      packagingMode: persistedMode(session) ?? 'LEGACY_ORIGINALS',
      allowLegacyWithoutFreeze: true,
      fallbackReason: 'FEATURE_DISABLED',
      freezeRequired: false,
      producerBarrierCompletedForRecovery: true,
    };
  }

  const mode = persistedMode(session);
  if (mode === 'STAGING_REQUIRED') {
    return {
      packagingMode: mode,
      allowLegacyWithoutFreeze: false,
      fallbackReason: null,
      freezeRequired: true,
      producerBarrierCompletedForRecovery: true,
    };
  }
  if (mode === 'LEGACY_ORIGINALS') {
    return {
      packagingMode: mode,
      allowLegacyWithoutFreeze: true,
      fallbackReason: 'LEGACY_SESSION_WITHOUT_PREP',
      freezeRequired: false,
      producerBarrierCompletedForRecovery: true,
    };
  }

  // Pre-migration / NULL: freeze signals imply modern packaging.
  const everFrozen =
    session.active_freeze_id != null ||
    session.capture_frozen_at != null ||
    (session.capture_freeze_generation ?? 0) > 0;
  if (everFrozen) {
    return {
      packagingMode: 'STAGING_REQUIRED',
      allowLegacyWithoutFreeze: false,
      fallbackReason: null,
      freezeRequired: true,
      producerBarrierCompletedForRecovery: session.active_freeze_id != null,
    };
  }

  return {
    packagingMode: 'LEGACY_ORIGINALS',
    allowLegacyWithoutFreeze: true,
    fallbackReason: 'LEGACY_SESSION_WITHOUT_PREP',
    freezeRequired: false,
    producerBarrierCompletedForRecovery: true,
  };
}
