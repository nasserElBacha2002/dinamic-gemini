/**
 * Phase 4.2 / 4.8 — Central evidence display eligibility.
 * Phase 4.8: when structural evidenceView is present, displayable is authoritative (fail-closed).
 */

import type { ResultEvidenceView, TraceabilityStatus } from '../types';

export interface EvidenceDisplayableOptions {
  /**
   * When false (default), legacy inference from traceabilityStatus/sourceImageId is blocked.
   * Set true only for pre-Phase-4.8 screens that lack structural evidenceView.
   */
  allowLegacyEvidenceFallback?: boolean;
}

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
 * Legacy fallback only when evidenceView is absent and allowLegacyEvidenceFallback is true.
 */
export function isEvidenceDisplayable(
  traceabilityStatus: TraceabilityStatus,
  hasValidEvidence: boolean | null | undefined,
  sourceImageId: string | null | undefined,
  evidenceView?: ResultEvidenceView | null,
  options?: EvidenceDisplayableOptions
): boolean {
  if (evidenceView != null) {
    return evidenceView.displayable === true;
  }
  if (options?.allowLegacyEvidenceFallback !== true) {
    return false;
  }
  return isLegacyEvidenceDisplayable(traceabilityStatus, hasValidEvidence, sourceImageId);
}

/** Resolve primary image URL from structural evidence contract when displayable. */
export function resolveStructuralEvidenceImageUrl(
  evidenceView?: ResultEvidenceView | null
): string | null {
  if (evidenceView?.displayable !== true) {
    return null;
  }
  const url = evidenceView.imageUrl != null ? String(evidenceView.imageUrl).trim() : '';
  return url.length > 0 ? url : null;
}
