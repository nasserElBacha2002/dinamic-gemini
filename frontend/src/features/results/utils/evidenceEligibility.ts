/**
 * Phase 4.2 / 4.8 — Central evidence display eligibility.
 * Phase 4.8: when structural evidenceView is present, displayable is authoritative (fail-closed).
 */

import type { ResultEvidenceView, TraceabilityStatus } from '../types';

/** Legacy path: true only when traceability is VALID and backend confirms has_valid_evidence. */
export function isLegacyEvidenceDisplayable(
  traceabilityStatus: TraceabilityStatus,
  hasValidEvidence: boolean | null | undefined,
  sourceImageId: string | null | undefined
): boolean {
  if (traceabilityStatus !== 'VALID') return false;
  if (hasValidEvidence !== true) return false;
  const sid = sourceImageId != null ? String(sourceImageId).trim() : '';
  return sid.length > 0;
}

/**
 * Fail-closed display gate.
 * Primary: evidenceView.displayable === true when structural view is present.
 * Legacy fallback (legacy_unavailable): only when evidenceView is absent.
 */
export function isEvidenceDisplayable(
  traceabilityStatus: TraceabilityStatus,
  hasValidEvidence: boolean | null | undefined,
  sourceImageId: string | null | undefined,
  evidenceView?: ResultEvidenceView | null
): boolean {
  if (evidenceView != null) {
    return evidenceView.displayable === true;
  }
  return isLegacyEvidenceDisplayable(traceabilityStatus, hasValidEvidence, sourceImageId);
}
