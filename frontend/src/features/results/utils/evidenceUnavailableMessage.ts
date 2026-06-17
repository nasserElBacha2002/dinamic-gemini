/**
 * Phase 4.2 — User-facing messages when evidence cannot be displayed.
 */

import type { TFunction } from 'i18next';
import type { TraceabilityStatus } from '../types';

export function evidenceUnavailableMessageKey(
  status: TraceabilityStatus
): 'results.evidence_panel.unavailable_missing' | 'results.evidence_panel.unavailable_invalid' | 'results.evidence_panel.unavailable_unvalidated' {
  if (status === 'MISSING') {
    return 'results.evidence_panel.unavailable_missing';
  }
  if (status === 'INVALID') {
    return 'results.evidence_panel.unavailable_invalid';
  }
  return 'results.evidence_panel.unavailable_unvalidated';
}

export function evidenceUnavailableMessage(
  status: TraceabilityStatus,
  t: TFunction
): string {
  return t(evidenceUnavailableMessageKey(status));
}
