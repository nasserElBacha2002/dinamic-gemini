/**
 * Phase 3: session producer barrier + drain exportability semantics.
 */

import { SessionProducerBarrier } from '../src/features/exportPrep/sessionProducerBarrier';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { ExportPrepRepository } from '../src/database/repositories/exportPrepRepository';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';
import { runPhotoStableProducers } from '../src/runtime/bootstrap/photoStableProducers';

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

  it('exportable only when all eligible READY', async () => {
    const { db, rows } = memoryDb();
    rows.set('p1', {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'READY',
      attempt_count: 1,
      lease_token: null,
      lease_expires_at: null,
      queued_at: '2026-01-01T00:00:00.000Z',
    });
    const photos = [
      {
        id: 'p1',
        capture_session_id: 's1',
        status: 'stable',
        uri: 'file://a',
        size: 1,
        width: 1,
        height: 1,
        sequence_number: 1,
        display_name: 'a.jpg',
      },
    ];
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        getSession: async () => ({
          id: 's1',
          active_freeze_id: 'f1',
          capture_freeze_generation: 2,
        }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async () => photos[0],
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    const snap = await queue.snapshotDrain('s1', {
      producerBarrierCompleted: true,
      timedOut: false,
      durationMs: 1,
    });
    expect(snap.exportable).toBe(true);
    expect(snap.freezeId).toBe('f1');
    expect(snap.freezeGeneration).toBe(2);
  });

  it('terminal-complete is not exportable', async () => {
    const { db, rows } = memoryDb();
    rows.set('p1', {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'FAILED_TERMINAL',
      attempt_count: 3,
      lease_token: null,
      lease_expires_at: null,
      queued_at: '2026-01-01T00:00:00.000Z',
    });
    const photos = [
      {
        id: 'p1',
        capture_session_id: 's1',
        status: 'stable',
        uri: 'file://a',
        size: 1,
        width: 1,
        height: 1,
        sequence_number: 1,
        display_name: 'a.jpg',
      },
    ];
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        getSession: async () => ({ id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async () => photos[0],
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    // Bypass ensure by calling snapshot only
    const snap = await queue.snapshotDrain('s1', {
      producerBarrierCompleted: true,
      timedOut: false,
      durationMs: 1,
    });
    expect(snap.exportable).toBe(false);
    expect(snap.failedTerminal).toBe(1);
    expect(snap.ready).toBe(0);
  });

  it('coalesces concurrent waitUntilExportable into one waiter', async () => {
    const { db, rows } = memoryDb();
    rows.set('p1', {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'READY',
      attempt_count: 1,
      lease_token: null,
      lease_expires_at: null,
      queued_at: '2026-01-01T00:00:00.000Z',
    });
    const photos = [
      {
        id: 'p1',
        capture_session_id: 's1',
        status: 'stable',
        uri: 'file://source/p1.jpg',
        size: 12,
        width: 1,
        height: 1,
        sequence_number: 1,
        display_name: 'p1.jpg',
      },
    ];
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
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        getSession: async () => ({ id: 's1', active_freeze_id: 'f1', capture_freeze_generation: 1 }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async () => photos[0],
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    jest.spyOn(queue, 'ensureJobsForEligiblePhotos').mockImplementation(ensureSpy as never);
    const [a, b] = await Promise.all([
      queue.waitUntilExportable('s1', { timeoutMs: 2_000, pollMs: 50 }),
      queue.waitUntilExportable('s1', { timeoutMs: 2_000, pollMs: 50 }),
    ]);
    expect(a.exportable).toBe(true);
    expect(b.exportable).toBe(true);
    expect(ensureSpy.mock.calls.length).toBeLessThanOrEqual(3);
  });
});
