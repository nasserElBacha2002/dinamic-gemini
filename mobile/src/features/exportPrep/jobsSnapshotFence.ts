import type { ExportPrepJobRow } from './exportPrepTypes';

/**
 * Identity of a READY (or any) prep job for snapshot fencing.
 * Any change to status / URI / size / SHA / timestamps invalidates reuse.
 */
export function jobSnapshotIdentity(job: ExportPrepJobRow): string {
  return [
    job.capture_photo_id,
    job.capture_session_id,
    job.status,
    job.staging_uri ?? '',
    job.export_file_name ?? '',
    String(job.size_bytes ?? ''),
    (job.sha256 ?? '').trim().toLowerCase(),
    job.ready_at ?? '',
    job.updated_at,
  ].join('\u001f');
}

/** Stable token over a job list (order-independent). */
export function buildJobsSnapshotToken(jobs: readonly ExportPrepJobRow[]): string {
  const parts = jobs.map(jobSnapshotIdentity).sort();
  // FNV-1a 32-bit — deterministic, no crypto dependency in RN core tests.
  let hash = 0x811c9dc5;
  const joined = parts.join('\u001e');
  for (let i = 0; i < joined.length; i += 1) {
    hash ^= joined.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return `jsnap_${(hash >>> 0).toString(16).padStart(8, '0')}_${jobs.length}`;
}

export type JobsSnapshotFenceMeta = {
  readonly token: string;
  readonly sessionId: string;
  readonly activeWorkersAtSnapshot: number;
  readonly jobCount: number;
};

/**
 * Snapshot is safe to attach only when ensure did not mutate jobs and no
 * in-flight workers own this session (READY is never claimed, but other
 * statuses could race if workers were still draining).
 */
export function canAttachJobsSnapshot(input: {
  readonly createdJobs: number;
  readonly requeuedJobs: number;
  readonly invalidatedReadyJobs: number;
  readonly activeWorkersForSession: number;
  readonly jobs: readonly ExportPrepJobRow[];
}): boolean {
  return (
    input.createdJobs === 0 &&
    input.requeuedJobs === 0 &&
    input.invalidatedReadyJobs === 0 &&
    input.activeWorkersForSession === 0 &&
    input.jobs.length > 0
  );
}

/**
 * Re-validate a previously attached snapshot against a live list.
 * Returns true when identities still match (safe to reuse without re-list).
 */
export function jobsSnapshotStillValid(
  snapshot: readonly ExportPrepJobRow[],
  token: string,
  live: readonly ExportPrepJobRow[],
): boolean {
  if (!token || snapshot.length === 0) return false;
  if (live.length !== snapshot.length) return false;
  if (buildJobsSnapshotToken(snapshot) !== token) return false;
  return buildJobsSnapshotToken(live) === token;
}

/**
 * Fail-closed check before packaging reuses ensure's jobsSnapshot.
 * When live jobs are unavailable, require zero active workers + matching token.
 *
 * Fence proof (no extra query required when liveJobs is supplied):
 * 1. ensure attaches snapshot only when canAttachJobsSnapshot (0 mutations, 0 workers).
 * 2. Token is FNV over job identities (status/uri/size/sha/timestamps).
 * 3. Before consume, assertJobsSnapshotConsumable re-hashes liveJobs and rejects
 *    any identity drift (status/sha/uri change) — so a mutation between snapshot
 *    and consume cannot silently reuse a stale list.
 */
export function assertJobsSnapshotConsumable(input: {
  readonly snapshot: readonly ExportPrepJobRow[];
  readonly token: string | undefined;
  readonly sessionId: string;
  readonly snapshotSessionId: string | undefined;
  readonly activeWorkersNow: number;
  readonly activeWorkersAtSnapshot: number | undefined;
  readonly liveJobs?: readonly ExportPrepJobRow[] | null;
}): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  if (!input.token) {
    return { ok: false, reason: 'missing_token' };
  }
  if (input.snapshotSessionId && input.snapshotSessionId !== input.sessionId) {
    return { ok: false, reason: 'session_mismatch' };
  }
  if ((input.activeWorkersAtSnapshot ?? 0) !== 0) {
    return { ok: false, reason: 'workers_at_snapshot' };
  }
  if (input.activeWorkersNow > 0) {
    return { ok: false, reason: 'workers_active_now' };
  }
  if (buildJobsSnapshotToken(input.snapshot) !== input.token) {
    return { ok: false, reason: 'token_mismatch_snapshot' };
  }
  if (input.liveJobs) {
    if (!jobsSnapshotStillValid(input.snapshot, input.token, input.liveJobs)) {
      return { ok: false, reason: 'live_identity_drift' };
    }
  }
  return { ok: true };
}
