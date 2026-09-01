import type { CaptureSessionRow } from '../../database/schema/captureSchema';

/**
 * Picks the most recently completed/frozen session for aisle metadata.
 * Priority: finished_at → capture_frozen_at → updated_at → started_at (descending).
 */
export function selectLatestSession(
  sessions: readonly CaptureSessionRow[],
): CaptureSessionRow {
  if (sessions.length === 0) {
    throw new Error('selectLatestSession: empty session list');
  }
  const score = (s: CaptureSessionRow): string =>
    s.finished_at ?? s.capture_frozen_at ?? s.updated_at ?? s.started_at ?? '';
  return [...sessions].sort((a, b) => score(b).localeCompare(score(a)))[0]!;
}
