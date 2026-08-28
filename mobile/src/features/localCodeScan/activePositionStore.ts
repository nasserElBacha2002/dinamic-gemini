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
/** Position label_ids already applied in this capture session (dedupe scope). */
const seenPositionLabelIdsBySession = new Map<string, Set<string>>();
/** Sessions whose seen/active state was hydrated from persisted drafts. */
const hydratedSessions = new Set<string>();

export type ApplyPositionScanResult =
  | { readonly kind: 'applied'; readonly state: ActivePositionState }
  | { readonly kind: 'duplicate'; readonly state: ActivePositionState }
  | { readonly kind: 'not_position' };

export type PositionDraftHydrationRow = {
  readonly position_snapshot_json: string | null;
  readonly position_detected: number | null;
  readonly updated_at?: string | null;
};

export function getActivePosition(captureSessionId: string): ActivePositionState | null {
  return bySession.get(captureSessionId) ?? null;
}

/** Clears only the current active position; preserves dedupe history for the session. */
export function clearCurrentPosition(captureSessionId: string): void {
  bySession.delete(captureSessionId);
}

/** Clears active position and dedupe history (session finished/cancelled). */
export function resetPositionSession(captureSessionId: string): void {
  bySession.delete(captureSessionId);
  seenPositionLabelIdsBySession.delete(captureSessionId);
  hydratedSessions.delete(captureSessionId);
}

export function clearAllActivePositions(): void {
  bySession.clear();
  seenPositionLabelIdsBySession.clear();
  hydratedSessions.clear();
}

/**
 * Simulates process restart: drops in-memory active/seen/hydration flags without touching DB drafts.
 * Tests and recovery paths use this before rehydrating from persisted drafts.
 */
export function clearInMemoryPositionState(captureSessionId: string): void {
  resetPositionSession(captureSessionId);
}

function seenForSession(captureSessionId: string): Set<string> {
  let seen = seenPositionLabelIdsBySession.get(captureSessionId);
  if (!seen) {
    seen = new Set<string>();
    seenPositionLabelIdsBySession.set(captureSessionId, seen);
  }
  return seen;
}

function labelIdFromPositionSnapshotJson(json: string | null | undefined): string | null {
  if (json == null || !String(json).trim()) return null;
  try {
    const parsed = JSON.parse(String(json)) as {
      labelId?: string;
      positionLabelId?: string;
    };
    const id = parsed.labelId ?? parsed.positionLabelId;
    return typeof id === 'string' && id.trim() ? id.trim().toUpperCase() : null;
  } catch {
    return null;
  }
}

function activePositionStateFromSnapshotJson(json: string): ActivePositionState | null {
  try {
    const parsed = JSON.parse(json) as ActivePositionState;
    if (typeof parsed.labelId !== 'string' || !parsed.labelId.trim()) return null;
    if (typeof parsed.rawPayload !== 'string' || !parsed.rawPayload.trim()) return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Lazy hydration: rebuild seen position label_ids (and current active position) from persisted drafts.
 * Call once per session before applyPositionScan when drafts may exist (e.g. after app restart).
 */
export function hydratePositionSessionFromDrafts(
  captureSessionId: string,
  drafts: readonly PositionDraftHydrationRow[],
): void {
  if (hydratedSessions.has(captureSessionId)) return;
  hydratedSessions.add(captureSessionId);

  const seen = seenForSession(captureSessionId);
  let latestActive: ActivePositionState | null = null;
  let latestOrder = -1;

  drafts.forEach((draft, index) => {
    if (!draft.position_detected || !draft.position_snapshot_json?.trim()) return;
    const labelId = labelIdFromPositionSnapshotJson(draft.position_snapshot_json);
    if (labelId) seen.add(labelId);

    const order = draft.updated_at ? Date.parse(draft.updated_at) : index;
    const resolvedOrder = Number.isFinite(order) ? order : index;
    if (resolvedOrder >= latestOrder) {
      const state = activePositionStateFromSnapshotJson(draft.position_snapshot_json);
      if (state) {
        latestActive = state;
        latestOrder = resolvedOrder;
      }
    }
  });

  if (latestActive && !bySession.has(captureSessionId)) {
    bySession.set(captureSessionId, latestActive);
  }
}

/**
 * If raw is a valid DINAMIC_POSITION payload, set/replace active position for the session.
 * Re-scanning the same position.label_id within the session is reported as duplicate.
 */
export function applyPositionScan(
  captureSessionId: string,
  raw: string,
): ApplyPositionScanResult {
  const parsed = parseDinamicPositionPayload(raw);
  if (!parsed) return { kind: 'not_position' };
  const labelKey = parsed.labelId.trim().toUpperCase();
  const seen = seenForSession(captureSessionId);
  if (seen.has(labelKey)) {
    const current = bySession.get(captureSessionId);
    if (current) {
      return { kind: 'duplicate', state: current };
    }
    return { kind: 'duplicate', state: activePositionFromParsed(parsed, raw.trim()) };
  }
  const next = activePositionFromParsed(parsed, raw.trim());
  bySession.set(captureSessionId, next);
  seen.add(labelKey);
  return { kind: 'applied', state: next };
}

export function positionCodeForExport(state: ActivePositionState | null): string {
  if (!state) return '';
  return state.displayName || state.labelId;
}
