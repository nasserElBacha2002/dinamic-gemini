/**
 * Active position forward-fill for capture sessions.
 * Authority for inventory count-once remains the backend.
 */

import type { ActivePositionState } from '../../core/positionLabelPayload';
import {
  activePositionFromParsed,
  parseDinamicPositionPayload,
} from '../../core/positionLabelPayload';

let active: ActivePositionState | null = null;

export function getActivePosition(): ActivePositionState | null {
  return active;
}

export function clearActivePosition(): void {
  active = null;
}

/**
 * If raw is a valid DINAMIC_POSITION payload, set/replace active position.
 * Returns the new active state or null when payload is not a position label.
 */
export function applyPositionScan(raw: string): ActivePositionState | null {
  const parsed = parseDinamicPositionPayload(raw);
  if (!parsed) return null;
  active = activePositionFromParsed(parsed, raw.trim());
  return active;
}

export function positionCodeForExport(state: ActivePositionState | null): string {
  if (!state) return '';
  return state.displayName || state.labelId;
}
