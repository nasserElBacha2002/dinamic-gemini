/**
 * Phase 4.2 — Central evidence display eligibility (mirrors backend is_traceability_evidence_displayable).
 */

import type { TraceabilityStatus } from '../types';

/** True only when traceability is VALID and backend confirms has_valid_evidence. */
export function isEvidenceDisplayable(
  traceabilityStatus: TraceabilityStatus,
  hasValidEvidence: boolean | null | undefined,
  sourceImageId: string | null | undefined
): boolean {
  if (traceabilityStatus !== 'VALID') return false;
  if (hasValidEvidence !== true) return false;
  const sid = sourceImageId != null ? String(sourceImageId).trim() : '';
  return sid.length > 0;
}
