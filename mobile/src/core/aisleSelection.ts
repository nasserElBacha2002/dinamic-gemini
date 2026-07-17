/**
 * Aisle selection is always allowed (business rule).
 * Remote/local status is informational only — never blocks UI selection.
 */

export type AisleBlockReason = null;

export interface AisleSelectionResult {
  readonly selectable: true;
  readonly reason: null;
}

export interface AisleSelectionInput {
  readonly id?: unknown;
  readonly code?: unknown;
  readonly status?: unknown;
  readonly is_active?: unknown;
  readonly isActive?: unknown;
  readonly latest_job?: unknown;
  readonly latestJob?: unknown;
}

/** @deprecated Local hints no longer affect selection. Kept for call-site compatibility. */
export interface LocalCaptureHint {
  readonly exclusiveCaptureOpen?: boolean;
  readonly exclusiveCaptureOnOtherAisle?: boolean;
}

export function normalizeStatus(raw: unknown): string {
  if (typeof raw !== 'string') {
    return '';
  }
  return raw.trim().toLowerCase().replace(/\s+/g, '_');
}

/** Soft-active for display only. Missing/null → treated as active in UI copy. */
export function normalizeIsActive(raw: unknown): boolean {
  if (raw === false || raw === 0 || raw === '0' || raw === 'false' || raw === 'False') {
    return false;
  }
  return true;
}

/**
 * Always allows aisle selection. Status/job/local capture never block.
 */
export function evaluateAisleSelection(
  _aisle?: AisleSelectionInput | null,
  _local?: LocalCaptureHint,
): AisleSelectionResult {
  return { selectable: true, reason: null };
}

export function aisleBlockReasonLabel(_reason: AisleBlockReason): string {
  return '';
}
