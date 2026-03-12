/**
 * Epic 3.1.B — Centralized traceability helpers.
 * Uses API-level traceability status (lowercase); for visible Result model use features/results.
 */

import { TRACEABILITY_STATUSES, type ApiTraceabilityStatus } from '../api/types';

export { TRACEABILITY_STATUSES, type ApiTraceabilityStatus };

/** Type guard: true if value is a known API traceability status. */
export function isTraceabilityStatus(
  value: string | null | undefined
): value is ApiTraceabilityStatus {
  return (
    value != null &&
    typeof value === 'string' &&
    (TRACEABILITY_STATUSES as readonly string[]).includes(value)
  );
}

/** Converts unknown backend value to ApiTraceabilityStatus or null (UI-safe). */
export function toTraceabilityStatus(
  value: unknown
): ApiTraceabilityStatus | null {
  if (value == null || typeof value !== 'string') return null;
  return isTraceabilityStatus(value) ? value : null;
}
