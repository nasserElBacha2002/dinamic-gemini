/**
 * Session-scoped active position forward-fill for capture sessions.
 * Authority for inventory count-once remains the backend.
 * Never claims cryptographic signature verification.
 */

import type { ActivePositionState } from '../../core/positionLabelPayload';
import {
  activePositionFromParsed,
  parseDinamicPositionPayload,
} from '../../core/positionLabelPayload';

/** Keyed by captureSessionId. */
const bySession = new Map<string, ActivePositionState>();

export function getActivePosition(captureSessionId: string): ActivePositionState | null {
  return bySession.get(captureSessionId) ?? null;
}

export function clearActivePosition(captureSessionId: string): void {
  bySession.delete(captureSessionId);
}

export function clearAllActivePositions(): void {
  bySession.clear();
}

/** Clear in-memory active position for a finished/cancelled capture session. */
export function resetSessionPosition(captureSessionId: string): void {
  clearActivePosition(captureSessionId);
}

/**
 * If raw is a valid DINAMIC_POSITION payload, set/replace active position for the session.
 * Returns the new active state or null when payload is not a position label.
 */
export function applyPositionScan(
  captureSessionId: string,
  raw: string,
): ActivePositionState | null {
  const parsed = parseDinamicPositionPayload(raw);
  if (!parsed) return null;
  const next = activePositionFromParsed(parsed, raw.trim());
  bySession.set(captureSessionId, next);
  return next;
}

export function positionCodeForExport(state: ActivePositionState | null): string {
  if (!state) return '';
  return state.displayName || state.labelId;
}
