import type { ExportPrepJobRow } from '../src/features/exportPrep/exportPrepTypes';
import {
  assertJobsSnapshotConsumable,
  buildJobsSnapshotToken,
  canAttachJobsSnapshot,
  jobSnapshotIdentity,
  jobsSnapshotStillValid,
} from '../src/features/exportPrep/jobsSnapshotFence';

function job(overrides: Partial<ExportPrepJobRow> = {}): ExportPrepJobRow {
  return {
    capture_photo_id: 'p1',
    capture_session_id: 's1',
    status: 'READY',
    source_uri: 'file://photo.jpg',
    staging_uri: 'file:///docs/export-staging/s1/0001_p1.jpg',
    export_file_name: '0001_p1.jpg',
    size_bytes: 12,
    sha256: 'c'.repeat(64),
    source_fingerprint: 'fp',
    error_code: null,
    error_message: null,
    attempt_count: 1,
    max_attempts: 3,
    lease_token: null,
    lease_expires_at: null,
    queued_at: '2026-01-01T00:00:00.000Z',
    started_at: '2026-01-01T00:00:00.000Z',
    ready_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    created_at: '2026-01-01T00:00:00.000Z',
    ...overrides,
  };
}

describe('jobsSnapshotFence', () => {
  test('token is stable for same identities regardless of order', () => {
    const a = job({ capture_photo_id: 'p1' });
    const b = job({ capture_photo_id: 'p2', export_file_name: '0002_p2.jpg' });
    expect(buildJobsSnapshotToken([a, b])).toBe(buildJobsSnapshotToken([b, a]));
    expect(jobSnapshotIdentity(a)).toContain('p1');
  });

  test('token changes when READY identity drifts', () => {
    const base = job();
    const drifted = job({ sha256: 'd'.repeat(64) });
    expect(buildJobsSnapshotToken([base])).not.toBe(buildJobsSnapshotToken([drifted]));
  });

  test('canAttachJobsSnapshot requires zero mutations and workers', () => {
    expect(
      canAttachJobsSnapshot({
        createdJobs: 0,
        requeuedJobs: 0,
        invalidatedReadyJobs: 0,
        activeWorkersForSession: 0,
        jobs: [job()],
      }),
    ).toBe(true);
    expect(
      canAttachJobsSnapshot({
        createdJobs: 1,
        requeuedJobs: 0,
        invalidatedReadyJobs: 0,
        activeWorkersForSession: 0,
        jobs: [job()],
      }),
    ).toBe(false);
    expect(
      canAttachJobsSnapshot({
        createdJobs: 0,
        requeuedJobs: 0,
        invalidatedReadyJobs: 0,
        activeWorkersForSession: 1,
        jobs: [job()],
      }),
    ).toBe(false);
  });

  test('assertJobsSnapshotConsumable is fail-closed', () => {
    const snapshot = [job()];
    const token = buildJobsSnapshotToken(snapshot);
    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
        liveJobs: snapshot,
      }),
    ).toEqual({ ok: true });

    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token: undefined,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
      }).ok,
    ).toBe(false);

    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 1,
        activeWorkersAtSnapshot: 0,
      }),
    ).toEqual({ ok: false, reason: 'workers_active_now' });

    expect(
      jobsSnapshotStillValid(snapshot, token, [job({ sha256: 'e'.repeat(64) })]),
    ).toBe(false);
  });

  test('mutation between snapshot and consume is detected (identity drift)', () => {
    // Prove: any READY field change after snapshot invalidates consume without
    // needing a separate "generation" column — token + liveJobs is sufficient.
    const snapshot = [job({ sha256: 'c'.repeat(64), updated_at: '2026-01-01T00:00:00.000Z' })];
    const token = buildJobsSnapshotToken(snapshot);
    const mutated = [job({ sha256: 'c'.repeat(64), updated_at: '2026-01-01T00:00:01.000Z' })];

    expect(canAttachJobsSnapshot({
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      activeWorkersForSession: 0,
      jobs: snapshot,
    })).toBe(true);

    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
        liveJobs: snapshot,
      }),
    ).toEqual({ ok: true });

    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
        liveJobs: mutated,
      }),
    ).toEqual({ ok: false, reason: 'live_identity_drift' });
  });

  test('revision drift invalidates snapshot without live list query', () => {
    const snapshot = [job()];
    const token = buildJobsSnapshotToken(snapshot);
    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
        snapshotRevision: 3,
        liveRevision: 3,
      }),
    ).toEqual({ ok: true });

    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
        snapshotRevision: 3,
        liveRevision: 4,
      }),
    ).toEqual({ ok: false, reason: 'revision_drift' });

    expect(
      assertJobsSnapshotConsumable({
        snapshot,
        token,
        sessionId: 's1',
        snapshotSessionId: 's1',
        activeWorkersNow: 0,
        activeWorkersAtSnapshot: 0,
        snapshotRevision: 3,
      }),
    ).toEqual({ ok: false, reason: 'revision_unchecked' });
  });
});
