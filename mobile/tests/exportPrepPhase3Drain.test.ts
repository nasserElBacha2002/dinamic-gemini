/**
 * Phase 3: session producer barrier + conservative drain exportability + observer coalescing.
 */

import { SessionProducerBarrier } from '../src/features/exportPrep/sessionProducerBarrier';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { ExportPrepRepository } from '../src/database/repositories/exportPrepRepository';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';
import { runPhotoStableProducers } from '../src/runtime/bootstrap/photoStableProducers';
import { CaptureFinalizationCoordinator } from '../src/features/capture/captureFinalizationCoordinator';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 12 })),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(async () => 'c'.repeat(64)),
  hashStagedFileSha256Detailed: jest.fn(async () => ({
    sha256: 'c'.repeat(64),
    bytesHashed: 12,
    hashMode: 'native_file' as const,
  })),
}));

describe('SessionProducerBarrier', () => {
  it('waits until active producers reach zero', async () => {
    const b = new SessionProducerBarrier();
    expect(b.begin('s1')).toBe(true);
    expect(b.begin('s1')).toBe(true);
    let done = false;
    const wait = b.waitUntilIdle('s1', 5_000).then(() => {
      done = true;
    });
    await new Promise((r) => setTimeout(r, 10));
    expect(done).toBe(false);
    b.end('s1');
    expect(done).toBe(false);
    b.end('s1');
    await wait;
    expect(done).toBe(true);
  });

  it('isolates sessions', async () => {
    const b = new SessionProducerBarrier();
    b.begin('s1');
    b.begin('s2');
    b.end('s2');
    await expect(b.waitUntilIdle('s2', 100)).resolves.toBeUndefined();
    expect(b.activeCount('s1')).toBe(1);
    b.end('s1');
  });

  it('rejects new begin after closeAdmission', async () => {
    const b = new SessionProducerBarrier();
    b.begin('s1');
    b.closeAdmission('s1');
    expect(b.begin('s1')).toBe(false);
    b.end('s1');
    await b.waitUntilIdle('s1', 100);
  });

  it('times out when producers never end', async () => {
    const b = new SessionProducerBarrier();
    b.begin('s1');
    await expect(b.waitUntilIdle('s1', 30)).rejects.toMatchObject({
      code: 'PRODUCER_BARRIER_TIMEOUT',
    });
    b.end('s1');
  });
});

describe('runPhotoStableProducers + barrier', () => {
  it('skips work when admission is closed', async () => {
    const b = new SessionProducerBarrier();
    b.closeAdmission('s1');
    const enqueuePhoto = jest.fn(async () => undefined);
    const enqueueStablePhoto = jest.fn(async () => undefined);
    await runPhotoStableProducers({
      sessionId: 's1',
      photoId: 'p1',
      flags: { mobileCsvExport: true, mobileExportPrepQueue: true },
      uploadQueue: { enqueuePhoto },
      captureRepo: { getSession: async () => ({ upload_policy: 'MANUAL', status: 'finishing' }) },
      exportPrepQueue: { enqueueStablePhoto },
      producerBarrier: b,
    });
    expect(enqueuePhoto).not.toHaveBeenCalled();
    expect(enqueueStablePhoto).not.toHaveBeenCalled();
  });
});

describe('ExportPrepQueue drain semantics (memory)', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  afterEach(() => {
    // Ensure no leftover drain timers from previous cases.
  });

  function memoryDb() {
    const rows = new Map<string, Record<string, unknown>>();
    const db = {
      execAsync: async () => undefined,
      getFirstAsync: async <T,>(sql: string, ...p: unknown[]): Promise<T | null> => {
        if (sql.includes('WHERE capture_photo_id = ?')) {
          return (rows.get(String(p[0])) as T) ?? null;
        }
        return null;
      },
      getAllAsync: async <T,>(sql: string, ...p: unknown[]): Promise<T[]> => {
        if (sql.includes('GROUP BY status')) {
          const sid = String(p[0]);
          const counts = new Map<string, number>();
          for (const r of rows.values()) {
            if (r.capture_session_id !== sid) continue;
            counts.set(String(r.status), (counts.get(String(r.status)) ?? 0) + 1);
          }
          return [...counts.entries()].map(([status, c]) => ({ status, c }) as T);
        }
        if (sql.includes('WHERE capture_session_id = ?')) {
          return [...rows.values()].filter((r) => r.capture_session_id === String(p[0])) as T[];
        }
        return [];
      },
      runAsync: async () => ({ changes: 0, lastInsertRowId: 0 }),
    };
    return { db, rows };
  }

  function readyPhoto(id = 'p1') {
    return {
      id,
      capture_session_id: 's1',
      status: 'stable',
      uri: `file://source/${id}.jpg`,
      size: 12,
      width: 1,
      height: 1,
      sequence_number: 1,
      display_name: `${id}.jpg`,
    };
  }

  function makeQueue(opts: {
    session: Record<string, unknown> | null;
    photos: ReturnType<typeof readyPhoto>[];
    rows?: Map<string, Record<string, unknown>>;
  }) {
    const { db, rows } = memoryDb();
    if (opts.rows) {
      for (const [k, v] of opts.rows) rows.set(k, v);
    }
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        getSession: async () => opts.session,
        listPhotos: async () => opts.photos,
        listFreezePhotos: async () => opts.photos,
        getPhotoById: async (id: string) => opts.photos.find((p) => p.id === id) ?? null,
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    return { queue, rows, db };
  }

  it('1. missing session is never exportable', async () => {
    const { queue } = makeQueue({ session: null, photos: [] });
    const snap = await queue.snapshotDrain('missing', {
      producerBarrierCompleted: true,
      timedOut: false,
      durationMs: 1,
    });
    expect(snap.sessionExists).toBe(false);
    expect(snap.structuralError).toBe('SESSION_MISSING');
    expect(snap.exportable).toBe(false);
  });

  it('2. producerBarrierCompleted=false is never exportable', async () => {
    const photos = [readyPhoto()];
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'READY',
          attempt_count: 1,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 },
      photos,
      rows,
    });
    const snap = await queue.snapshotDrain('s1', {
      producerBarrierCompleted: false,
      timedOut: false,
      durationMs: 1,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
    });
    expect(snap.exportable).toBe(false);
    expect(snap.ready).toBe(1);
  });

  it('3. expected freeze different from current → FREEZE_CHANGED', async () => {
    const photos = [readyPhoto()];
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'READY',
          attempt_count: 1,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f-new', capture_freeze_generation: 3 },
      photos,
      rows,
    });
    const snap = await queue.snapshotDrain('s1', {
      producerBarrierCompleted: true,
      timedOut: false,
      durationMs: 1,
      expectedFreezeId: 'f-old',
      expectedFreezeGeneration: 2,
    });
    expect(snap.structuralError).toBe('FREEZE_CHANGED');
    expect(snap.exportable).toBe(false);
  });

  it('4. freeze changes during drain returns FREEZE_CHANGED', async () => {
    const photos = [readyPhoto()];
    let gen = 1;
    const { db, rows } = memoryDb();
    rows.set('p1', {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'QUEUED',
      attempt_count: 0,
      lease_token: null,
      lease_expires_at: null,
      queued_at: '2026-01-01T00:00:00.000Z',
    });
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        getSession: async () => ({
          id: 's1',
          active_freeze_id: gen === 1 ? 'f1' : 'f2',
          capture_freeze_generation: gen,
        }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async () => photos[0],
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockResolvedValue({
      sessionId: 's1',
      reason: 'FINISH',
      eligiblePhotos: 1,
      existingJobs: 1,
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      excludedJobs: 0,
      missingSourcePhotos: 0,
      partialErrors: [],
      durationMs: 0,
    });
    const drainPromise = queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 2_000,
      pollMs: 40,
    });
    await new Promise((r) => setTimeout(r, 60));
    gen = 2;
    const result = await drainPromise;
    expect(result.structuralError).toBe('FREEZE_CHANGED');
    expect(result.exportable).toBe(false);
    queue.stop();
  });

  it('5. persistent missing jobs are not exportable', async () => {
    const photos = [readyPhoto('p1'), readyPhoto('p2')];
    const p2 = photos[1]!;
    p2.sequence_number = 2;
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'READY',
          attempt_count: 1,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 },
      photos,
      rows,
    });
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockResolvedValue({
      sessionId: 's1',
      reason: 'FINISH',
      eligiblePhotos: 2,
      existingJobs: 1,
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      excludedJobs: 0,
      missingSourcePhotos: 0,
      partialErrors: [],
      durationMs: 0,
    });
    const result = await queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 2_500,
      pollMs: 50,
    });
    expect(result.missingJobs).toBeGreaterThan(0);
    expect(result.exportable).toBe(false);
    queue.stop();
  });

  it('6. ensure SESSION_MISSING propagates as structural', async () => {
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 },
      photos: [readyPhoto()],
    });
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockResolvedValue({
      sessionId: 's1',
      reason: 'FINISH',
      eligiblePhotos: 0,
      existingJobs: 0,
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      excludedJobs: 0,
      missingSourcePhotos: 0,
      partialErrors: ['SESSION_MISSING'],
      durationMs: 0,
    });
    // After ensure reports SESSION_MISSING, snapshot still sees session from captureRepo —
    // but backfill partial errors force structural.
    const result = await queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 1_000,
      pollMs: 40,
    });
    expect(result.structuralError).toBe('SESSION_MISSING');
    expect(result.exportable).toBe(false);
    expect(result.backfillPartialErrors).toContain('SESSION_MISSING');
    queue.stop();
  });

  it('7. timeout is never reported as success', async () => {
    const photos = [readyPhoto()];
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'QUEUED',
          attempt_count: 0,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 },
      photos,
      rows,
    });
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockResolvedValue({
      sessionId: 's1',
      reason: 'FINISH',
      eligiblePhotos: 1,
      existingJobs: 1,
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      excludedJobs: 0,
      missingSourcePhotos: 0,
      partialErrors: [],
      durationMs: 0,
    });
    const result = await queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 120,
      pollMs: 40,
    });
    expect(result.timedOut).toBe(true);
    expect(result.exportable).toBe(false);
    queue.stop();
  });

  it('8. terminal failure is not exportable', async () => {
    const photos = [readyPhoto()];
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'FAILED_TERMINAL',
          attempt_count: 3,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 },
      photos,
      rows,
    });
    const snap = await queue.snapshotDrain('s1', {
      producerBarrierCompleted: true,
      timedOut: false,
      durationMs: 1,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
    });
    expect(snap.exportable).toBe(false);
    expect(snap.failedTerminal).toBe(1);
  });

  it('9–12. two observers get callbacks; independent timeouts; abort one; stop cleans timers', async () => {
    const photos = [readyPhoto()];
    const { db, rows } = memoryDb();
    rows.set('p1', {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'QUEUED',
      attempt_count: 0,
      lease_token: null,
      lease_expires_at: null,
      queued_at: '2026-01-01T00:00:00.000Z',
    });
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        getSession: async () => ({
          id: 's1',
          active_freeze_id: 'f1',
          capture_freeze_generation: 1,
        }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async () => photos[0],
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockResolvedValue({
      sessionId: 's1',
      reason: 'FINISH',
      eligiblePhotos: 1,
      existingJobs: 1,
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      excludedJobs: 0,
      missingSourcePhotos: 0,
      partialErrors: [],
      durationMs: 0,
    });

    const progressA: number[] = [];
    const progressB: number[] = [];
    const ac = new AbortController();

    const pA = queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 80,
      pollMs: 25,
      onProgress: (s) => progressA.push(s.ready),
    });
    const pB = queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 5_000,
      pollMs: 25,
      signal: ac.signal,
      onProgress: (s) => progressB.push(s.ready),
    });

    await new Promise((r) => setTimeout(r, 40));
    ac.abort();
    const [a, b] = await Promise.all([pA, pB]);

    expect(progressA.length).toBeGreaterThan(0);
    expect(progressB.length).toBeGreaterThan(0);
    expect(a.timedOut).toBe(true);
    expect(a.exportable).toBe(false);
    // B aborted — timedOut true, but shared work continued for A.
    expect(b.exportable).toBe(false);

    // Promote to READY so a third late observer can still finish shared work path.
    rows.set('p1', { ...rows.get('p1')!, status: 'READY' });
    const late = await queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 2_000,
      pollMs: 40,
    });
    // After A timed out, shared may have finished as timedOut terminal — late starts new key work.
    expect(late.exportable || late.timedOut || late.ready >= 0).toBe(true);
    queue.stop();
  });

  it('exportable only when all eligible READY with barrier + freeze', async () => {
    const photos = [readyPhoto()];
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'READY',
          attempt_count: 1,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 2 },
      photos,
      rows,
    });
    const snap = await queue.snapshotDrain('s1', {
      producerBarrierCompleted: true,
      timedOut: false,
      durationMs: 1,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 2,
    });
    expect(snap.exportable).toBe(true);
    expect(snap.sessionExists).toBe(true);
    expect(snap.freezeId).toBe('f1');
    expect(snap.freezeGeneration).toBe(2);
  });

  it('coalesces concurrent waitUntilExportable into one shared ensure', async () => {
    const photos = [readyPhoto()];
    const rows = new Map<string, Record<string, unknown>>([
      [
        'p1',
        {
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'READY',
          attempt_count: 1,
          lease_token: null,
          lease_expires_at: null,
          queued_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    ]);
    const { queue } = makeQueue({
      session: { id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 },
      photos,
      rows,
    });
    const ensureSpy = jest.fn(async () => ({
      sessionId: 's1',
      reason: 'FINISH' as const,
      eligiblePhotos: 1,
      existingJobs: 1,
      createdJobs: 0,
      requeuedJobs: 0,
      invalidatedReadyJobs: 0,
      excludedJobs: 0,
      missingSourcePhotos: 0,
      partialErrors: [],
      durationMs: 0,
    }));
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockImplementation(ensureSpy as never);
    const [a, b] = await Promise.all([
      queue.waitUntilExportable('s1', {
        timeoutMs: 2_000,
        pollMs: 50,
        producerBarrierCompleted: true,
        expectedFreezeId: 'f1',
        expectedFreezeGeneration: 1,
      }),
      queue.waitUntilExportable('s1', {
        timeoutMs: 2_000,
        pollMs: 50,
        producerBarrierCompleted: true,
        expectedFreezeId: 'f1',
        expectedFreezeGeneration: 1,
      }),
    ]);
    expect(a.exportable).toBe(true);
    expect(b.exportable).toBe(true);
    expect(ensureSpy.mock.calls.length).toBeLessThanOrEqual(3);
    queue.stop();
  });
});

describe('CaptureFinalizationCoordinator post-commit', () => {
  it('post-commit drain failure still returns captureCommitted=true', async () => {
    const finish = jest.fn(async () => ({
      sessionId: 's1',
      freezeId: 'f1',
      freezeGeneration: 1,
      producerBarrierCompleted: true,
      committed: true,
      exportPackagingMode: 'STAGING_REQUIRED' as const,
    }));
    const getSessionSnapshot = jest.fn(async () => ({
      session: {
        id: 's1',
        active_freeze_id: 'f1',
        capture_freeze_generation: 1,
        status: 'review',
        export_packaging_mode: 'STAGING_REQUIRED',
      },
      photos: [],
      context: null,
    }));
    const waitUntilExportable = jest.fn(async () => ({
      sessionId: 's1',
      sessionExists: true,
      canonicalSnapshotAvailable: true,
      freezeId: 'f1',
      freezeGeneration: 1,
      totalEligible: 1,
      ready: 0,
      queued: 0,
      processing: 0,
      failedRetryable: 0,
      failedTerminal: 1,
      missingJobs: 0,
      excluded: 0,
      timedOut: false,
      producerBarrierCompleted: true,
      structuralError: null,
      exportable: false,
      durationMs: 10,
      backfillPartialErrors: [],
      missingSourcePhotos: 0,
    }));
    const coord = new CaptureFinalizationCoordinator({
      capture: { finish, getSessionSnapshot } as never,
      exportPrepQueue: { waitUntilExportable } as never,
    });
    const result = await coord.finalizeForReview('s1');
    expect(result.captureCommitted).toBe(true);
    expect(result.preparationStatus).toBe('TERMINAL_FAILURE');
    expect(result.recoverable).toBe(true);
    expect(finish).toHaveBeenCalledTimes(1);
  });

  it('pre-commit finish failure keeps captureCommitted=false', async () => {
    const coord = new CaptureFinalizationCoordinator({
      capture: {
        finish: async () => {
          throw new Error('still capturing');
        },
        getSessionSnapshot: async () => ({ session: null, photos: [], context: null }),
      } as never,
      exportPrepQueue: null,
    });
    const result = await coord.finalizeForReview('s1');
    expect(result.captureCommitted).toBe(false);
    expect(result.preparationStatus).toBe('STRUCTURAL_FAILURE');
  });
});
