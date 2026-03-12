/**
 * Epic 3 — Safe mapping from visible TraceabilityStatus to API chip status.
 * Keeps the Results overview UI independent of raw API type casting.
 */

import type { TraceabilityStatus } from '../types';
import type { ApiTraceabilityStatus } from '../../../api/types';

const VISIBLE_TO_API: Record<TraceabilityStatus, ApiTraceabilityStatus> = {
  VALID: 'valid',
  MISSING: 'missing',
  INVALID: 'invalid',
  UNVALIDATED: 'unvalidated',
};

/**
 * Map visible-model traceability status to the value expected by TraceabilityChip (API shape).
 * Use this instead of casting in Result-centric components.
 */
export function visibleTraceabilityToApiStatus(
  status: TraceabilityStatus
): ApiTraceabilityStatus {
  return VISIBLE_TO_API[status];
}
