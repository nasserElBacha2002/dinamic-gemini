/**
 * Epic 3.1.B — Centralized traceability helpers.
 * Single source for allowed values, type guard, and UI-safe conversion.
 * Re-exports backend-aligned types from API shared; add runtime/UI helpers here.
 */

import { TRACEABILITY_STATUSES, type TraceabilityStatus } from '../api/types';

export { TRACEABILITY_STATUSES, type TraceabilityStatus };

/** Type guard: true if value is a known traceability status. */
export function isTraceabilityStatus(
  value: string | null | undefined
): value is TraceabilityStatus {
  return (
    value != null &&
    typeof value === 'string' &&
    (TRACEABILITY_STATUSES as readonly string[]).includes(value)
  );
}

/** Converts unknown backend value to TraceabilityStatus or null (UI-safe). */
export function toTraceabilityStatus(
  value: unknown
): TraceabilityStatus | null {
  if (value == null || typeof value !== 'string') return null;
  return isTraceabilityStatus(value) ? value : null;
}
