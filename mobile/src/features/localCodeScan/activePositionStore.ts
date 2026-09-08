/**
 * Session-scoped active position forward-fill for capture sessions.
 * Authority for inventory count-once remains the backend.
 * Never claims cryptographic signature verification.
 */

import type { ActivePositionState } from '../../core/positionLabelPayload';
import {
  activePositionFromParsed,
  parseActivePositionStateJson,
  parseDinamicPositionPayload,
} from '../../core/positionLabelPayload';

/** Keyed by captureSessionId. */
const bySession = new Map<string, ActivePositionState>();
/** Canonical position identities observed in this capture session (audit/dedupe scope). */
const seenPositionIdentitiesBySession = new Map<string, Set<string>>();
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
  seenPositionIdentitiesBySession.delete(captureSessionId);
  hydratedSessions.delete(captureSessionId);
}

export function clearAllActivePositions(): void {
  bySession.clear();
  seenPositionIdentitiesBySession.clear();
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
  let seen = seenPositionIdentitiesBySession.get(captureSessionId);
  if (!seen) {
    seen = new Set<string>();
    seenPositionIdentitiesBySession.set(captureSessionId, seen);
  }
  return seen;
}

function activePositionStateFromSnapshotJson(
  captureSessionId: string,
  json: string,
): ActivePositionState | null {
  try {
    const value: unknown = JSON.parse(json);
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
    const row = value as Record<string, unknown>;
    const inventoryId = typeof row.inventoryId === 'string' ? row.inventoryId : null;
    const aisleLocalId = typeof row.aisleLocalId === 'string' ? row.aisleLocalId : null;
    const parsed = parseActivePositionStateJson(json, {
      captureSessionId,
      inventoryId,
      aisleLocalId,
    });
    return parsed.ok ? parsed.state : null;
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
    const order = draft.updated_at ? Date.parse(draft.updated_at) : index;
    const resolvedOrder = Number.isFinite(order) ? order : index;
    if (resolvedOrder >= latestOrder) {
      const state = activePositionStateFromSnapshotJson(
        captureSessionId,
        draft.position_snapshot_json,
      );
      if (state) {
        seen.add(positionIdentity(state));
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
  const next = activePositionFromParsed(parsed, raw.trim(), {
    localRecognitionId: `legacy:${captureSessionId}:${parsed.canonicalKey}`,
    captureSessionId,
    inventoryId: null,
    aisleLocalId: null,
    source: 'LOCAL_CODE_SCAN',
  });
  const prepared = preparePositionActivation(next);
  commitPositionActivation(prepared);
  return prepared;
}

export type PreparedPositionActivation =
  | { readonly kind: 'applied'; readonly state: ActivePositionState }
  | { readonly kind: 'duplicate'; readonly state: ActivePositionState };

/** Last confirmed transition wins; historical A may be reactivated after B. */
export function preparePositionActivation(
  next: ActivePositionState,
): PreparedPositionActivation {
  const current = bySession.get(next.captureSessionId);
  if (current && positionIdentity(current) === positionIdentity(next)) {
    return { kind: 'duplicate', state: current };
  }
  return { kind: 'applied', state: next };
}

/** Call only after the corresponding SQLite unit of work commits. */
export function commitPositionActivation(prepared: PreparedPositionActivation): void {
  if (prepared.kind === 'duplicate') return;
  bySession.set(prepared.state.captureSessionId, prepared.state);
  seenForSession(prepared.state.captureSessionId).add(positionIdentity(prepared.state));
}

export function restorePositionSession(state: ActivePositionState): void {
  bySession.set(state.captureSessionId, state);
  seenForSession(state.captureSessionId).add(positionIdentity(state));
  hydratedSessions.add(state.captureSessionId);
}

export async function activatePosition(
  next: ActivePositionState,
  persist: (state: ActivePositionState) => Promise<void>,
): Promise<PreparedPositionActivation> {
  const prepared = preparePositionActivation(next);
  if (prepared.kind === 'duplicate') return prepared;
  await persist(prepared.state);
  commitPositionActivation(prepared);
  return prepared;
}

function positionIdentity(position: ActivePositionState): string {
  return [
    position.normalizedCode,
    position.captureSessionId,
    position.aisleLocalId ?? '',
    position.profileVersion ?? '',
    position.clientSupplierId ?? '',
  ].join('|');
}

export function positionCodeForExport(state: ActivePositionState | null): string {
  if (!state) return '';
  return state.displayName || state.labelId;
}
