/**
 * Integration-level tests for ExportPrepRepository fencing + coordinator using an
 * in-memory row store (persisted Map state — not string-SQL inspection).
 */

import {
  ExportPrepFenceError,
  ExportPrepRepository,
  isValidStagedSha256,
} from '../src/database/repositories/exportPrepRepository';
import { ExportPrepPhotoCoordinator } from '../src/features/exportPrep/exportPrepPhotoCoordinator';
import type { ExportPrepJobRow } from '../src/features/exportPrep/exportPrepTypes';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async (uri: string) => {
    const u = String(uri);
    if (u.includes('missing')) return { exists: false };
    if (u.includes('export-staging') || u.includes('source')) {
      return { exists: true, size: 12, modificationTime: Date.now() / 1000 };
    }
    return { exists: true, size: 12 };
  }),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello-staged').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

const VALID_SHA = 'a'.repeat(64);

type Row = ExportPrepJobRow & Record<string, unknown>;

function createMemoryExportPrepDb() {
  const rows = new Map<string, Row>();

  const bind = (sql: string, params: unknown[]): unknown[] => {
    // expo-sqlite: runAsync(sql, ...params) — our repo spreads params.
    return params;
  };

  const db = {
    execAsync: async (_sql: string) => undefined,
    getFirstAsync: async <T,>(sql: string, ...params: unknown[]): Promise<T | null> => {
      const p = bind(sql, params);
      if (sql.includes('WHERE capture_photo_id = ?') && !sql.includes('ORDER BY')) {
        return (rows.get(String(p[0])) as T) ?? null;
      }
      if (sql.includes('FROM export_prep_jobs') && sql.includes('LIMIT 1')) {
        const now = String(p[p.length - 1] ?? p[0]);
        const sessionFilter = sql.includes('capture_session_id = ?') ? String(p[0]) : null;
        const candidates = [...rows.values()]
          .filter((r) => (sessionFilter ? r.capture_session_id === sessionFilter : true))
          .filter((r) => {
            if (r.status === 'QUEUED' || r.status === 'FAILED_RETRYABLE') return true;
            if (['PREPARING', 'SCANNING', 'VALIDATING'].includes(r.status)) {
              return (
                r.lease_expires_at == null ||
                r.lease_expires_at < now ||
                r.lease_token == null
              );
            }
            return false;
          })
          .sort((a, b) => {
            const rank = (s: string) =>
              s === 'QUEUED' ? 0 : s === 'FAILED_RETRYABLE' ? 1 : 2;
            const d = rank(a.status) - rank(b.status);
            if (d !== 0) return d;
            return a.queued_at.localeCompare(b.queued_at);
          });
        return (candidates[0] as T) ?? null;
      }
      return null;
    },
    getAllAsync: async <T,>(sql: string, ...params: unknown[]): Promise<T[]> => {
      const p = bind(sql, params);
      if (sql.includes('GROUP BY status')) {
        const sid = String(p[0]);
        const counts = new Map<string, number>();
        for (const r of rows.values()) {
          if (r.capture_session_id !== sid) continue;
          counts.set(r.status, (counts.get(r.status) ?? 0) + 1);
        }
        return [...counts.entries()].map(([status, c]) => ({ status, c }) as T);
      }
      if (sql.includes('WHERE capture_session_id = ?')) {
        const sid = String(p[0]);
        return [...rows.values()]
          .filter((r) => r.capture_session_id === sid)
          .sort((a, b) => a.queued_at.localeCompare(b.queued_at)) as T[];
      }
      return [];
    },
    runAsync: async (sql: string, ...params: unknown[]) => {
      const p = bind(sql, params);
      if (sql.includes('INSERT INTO export_prep_jobs')) {
        const id = String(p[0]);
        const row: Row = {
          capture_photo_id: id,
          capture_session_id: String(p[1]),
          status: 'QUEUED',
          source_uri: String(p[2]),
          staging_uri: null,
          export_file_name: (p[3] as string | null) ?? null,
          size_bytes: null,
          sha256: null,
          source_fingerprint: (p[4] as string | null) ?? null,
          error_code: null,
          error_message: null,
          attempt_count: 0,
          max_attempts: 3,
          lease_token: null,
          lease_expires_at: null,
          queued_at: String(p[5]),
          started_at: null,
          ready_at: null,
          updated_at: String(p[6]),
          created_at: String(p[7]),
        };
        rows.set(id, row);
        return { changes: 1, lastInsertRowId: 1 };
      }

      if (sql.includes('attempt_count = attempt_count + 1') && sql.includes('lease_token = ?')) {
        // claim UPDATE
        const leaseToken = String(p[0]);
        const expires = String(p[1]);
        const now = String(p[2]);
        const updatedAt = String(p[3]);
        const photoId = String(p[4]);
        const nowCmp = String(p[5]);
        const cur = rows.get(photoId);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        const claimable =
          cur.status === 'QUEUED' ||
          cur.status === 'FAILED_RETRYABLE' ||
          (['PREPARING', 'SCANNING', 'VALIDATING'].includes(cur.status) &&
            (cur.lease_expires_at == null ||
              cur.lease_expires_at < nowCmp ||
              cur.lease_token == null));
        if (!claimable) return { changes: 0, lastInsertRowId: 0 };
        rows.set(photoId, {
          ...cur,
          status: 'PREPARING',
          lease_token: leaseToken,
          lease_expires_at: expires,
          attempt_count: cur.attempt_count + 1,
          started_at: cur.started_at ?? now,
          updated_at: updatedAt,
          error_code: null,
          error_message: null,
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      const photoIdLast = String(p[p.length - 2] ?? '');
      const leaseLast = String(p[p.length - 1] ?? '');

      const fencedMatch = (id: string, token: string, allowed: string[]): Row | null => {
        const cur = rows.get(id);
        if (!cur || cur.lease_token !== token) return null;
        if (!allowed.includes(cur.status)) return null;
        return cur;
      };

      if (sql.includes('lease_expires_at = ?') && sql.includes("status IN ('PREPARING', 'SCANNING', 'VALIDATING')") && !sql.includes('status =')) {
        // renewLease — params: expires, now, photoId, leaseToken
        const cur = fencedMatch(String(p[2]), String(p[3]), ['PREPARING', 'SCANNING', 'VALIDATING']);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(cur.capture_photo_id, {
          ...cur,
          lease_expires_at: String(p[0]),
          updated_at: String(p[1]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("status = 'SCANNING'") && sql.includes('staging_uri = ?')) {
        const cur = fencedMatch(String(p[5]), String(p[6]), ['PREPARING']);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(cur.capture_photo_id, {
          ...cur,
          status: 'SCANNING',
          staging_uri: String(p[0]),
          export_file_name: String(p[1]),
          size_bytes: Number(p[2]),
          lease_expires_at: String(p[3]),
          updated_at: String(p[4]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("status = 'VALIDATING'") && sql.includes("status = 'SCANNING'")) {
        const cur = fencedMatch(String(p[2]), String(p[3]), ['SCANNING']);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(cur.capture_photo_id, {
          ...cur,
          status: 'VALIDATING',
          lease_expires_at: String(p[0]),
          updated_at: String(p[1]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("status = 'READY'") && sql.includes('AND lease_token = ?')) {
        const cur = fencedMatch(String(p[6]), String(p[7]), ['VALIDATING']);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(cur.capture_photo_id, {
          ...cur,
          status: 'READY',
          staging_uri: String(p[0]),
          export_file_name: String(p[1]),
          size_bytes: Number(p[2]),
          sha256: String(p[3]),
          error_code: null,
          error_message: null,
          lease_token: null,
          lease_expires_at: null,
          ready_at: String(p[4]),
          updated_at: String(p[5]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes('AND lease_token = ?') && sql.includes("status IN ('PREPARING', 'SCANNING', 'VALIDATING')") && sql.includes('error_code')) {
        const status = String(p[0]);
        const cur = fencedMatch(String(p[4]), String(p[5]), ['PREPARING', 'SCANNING', 'VALIDATING']);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(cur.capture_photo_id, {
          ...cur,
          status: status as ExportPrepJobRow['status'],
          error_code: String(p[1]),
          error_message: String(p[2]),
          lease_token: null,
          lease_expires_at: null,
          updated_at: String(p[3]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("status = 'EXCLUDED'") && !sql.includes("status = 'QUEUED'")) {
        const id = String(p[1]);
        const cur = rows.get(id);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(id, {
          ...cur,
          status: 'EXCLUDED',
          lease_token: null,
          lease_expires_at: null,
          error_code: null,
          error_message: null,
          updated_at: String(p[0]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("status = 'FAILED_RETRYABLE'") && sql.includes("status = 'READY'")) {
        const id = String(p[3]);
        const cur = rows.get(id);
        if (!cur || cur.status !== 'READY') return { changes: 0, lastInsertRowId: 0 };
        rows.set(id, {
          ...cur,
          staging_uri: null,
          size_bytes: null,
          sha256: null,
          status: 'FAILED_RETRYABLE',
          error_code: String(p[0]),
          error_message: String(p[1]),
          lease_token: null,
          lease_expires_at: null,
          ready_at: null,
          updated_at: String(p[2]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("AND status = 'EXCLUDED'")) {
        const id = String(p[1]);
        const cur = rows.get(id);
        if (!cur || cur.status !== 'EXCLUDED') return { changes: 0, lastInsertRowId: 0 };
        rows.set(id, {
          ...cur,
          status: 'QUEUED',
          lease_token: null,
          lease_expires_at: null,
          error_code: null,
          error_message: null,
          ready_at: null,
          updated_at: String(p[0]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes("AND status = 'QUEUED'") && sql.includes("status = 'READY'")) {
        const id = String(p[2]);
        const cur = rows.get(id);
        if (
          !cur ||
          cur.status !== 'QUEUED' ||
          !cur.staging_uri ||
          !cur.sha256 ||
          !(cur.size_bytes && cur.size_bytes > 0) ||
          !cur.export_file_name
        ) {
          return { changes: 0, lastInsertRowId: 0 };
        }
        rows.set(id, {
          ...cur,
          status: 'READY',
          lease_token: null,
          lease_expires_at: null,
          ready_at: String(p[0]),
          updated_at: String(p[1]),
          error_code: null,
          error_message: null,
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes('FAILED_RETRYABLE') && sql.includes('FAILED_TERMINAL') && sql.includes('QUEUED')) {
        if (sql.includes('capture_session_id')) {
          const sid = String(p[1]);
          let n = 0;
          for (const [id, cur] of rows) {
            if (
              cur.capture_session_id === sid &&
              (cur.status === 'FAILED_RETRYABLE' || cur.status === 'FAILED_TERMINAL')
            ) {
              rows.set(id, {
                ...cur,
                status: 'QUEUED',
                lease_token: null,
                lease_expires_at: null,
                error_code: null,
                error_message: null,
                attempt_count: 0,
                updated_at: String(p[0]),
              });
              n += 1;
            }
          }
          return { changes: n, lastInsertRowId: 0 };
        }
        const id = String(p[1]);
        const cur = rows.get(id);
        if (!cur || (cur.status !== 'FAILED_RETRYABLE' && cur.status !== 'FAILED_TERMINAL')) {
          return { changes: 0, lastInsertRowId: 0 };
        }
        rows.set(id, {
          ...cur,
          status: 'QUEUED',
          lease_token: null,
          lease_expires_at: null,
          error_code: null,
          error_message: null,
          updated_at: String(p[0]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      if (sql.includes('recover') || (sql.includes("status = 'QUEUED'") && sql.includes('PREPARING'))) {
        let n = 0;
        for (const [id, cur] of rows) {
          if (['PREPARING', 'SCANNING', 'VALIDATING'].includes(cur.status)) {
            rows.set(id, {
              ...cur,
              status: 'QUEUED',
              lease_token: null,
              lease_expires_at: null,
              updated_at: String(p[0]),
            });
            n += 1;
          }
        }
        return { changes: n, lastInsertRowId: 0 };
      }

      if (sql.includes('DELETE FROM export_prep_jobs')) {
        const sid = String(p[0]);
        for (const [id, cur] of [...rows.entries()]) {
          if (cur.capture_session_id === sid) rows.delete(id);
        }
        return { changes: 1, lastInsertRowId: 0 };
      }

      // enqueueIdempotent requeue UPDATE (no lease fence)
      if (sql.includes("status = 'QUEUED'") && sql.includes('source_uri = ?')) {
        const id = String(p[4]);
        const cur = rows.get(id);
        if (!cur) return { changes: 0, lastInsertRowId: 0 };
        rows.set(id, {
          ...cur,
          status: 'QUEUED',
          source_uri: String(p[0]),
          source_fingerprint: (p[1] as string | null) ?? cur.source_fingerprint,
          export_file_name: (p[2] as string | null) ?? cur.export_file_name,
          lease_token: null,
          lease_expires_at: null,
          error_code: null,
          error_message: null,
          updated_at: String(p[3]),
        });
        return { changes: 1, lastInsertRowId: 0 };
      }

      void photoIdLast;
      void leaseLast;
      return { changes: 0, lastInsertRowId: 0 };
    },
  };

  return { db, rows };
}

describe('ExportPrepRepository fencing (memory store)', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  it('claimNext returns non-null lease_token', async () => {
    const { db } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: 'fp',
      exportFileName: '0001_p1.jpg',
    });
    const job = await repo.claimNext('s1');
    expect(job?.lease_token).toBeTruthy();
    expect(job?.status).toBe('PREPARING');
  });

  it('rejects stale worker markReady after lease reclaim', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: 'fp',
      exportFileName: '0001_p1.jpg',
    });
    const first = await repo.claimNext('s1');
    expect(first?.lease_token).toBeTruthy();
    // Expire lease
    rows.set('p1', {
      ...rows.get('p1')!,
      lease_expires_at: '2000-01-01T00:00:00.000Z',
    });
    const second = await repo.claimNext('s1');
    expect(second?.lease_token).toBeTruthy();
    expect(second!.lease_token).not.toBe(first!.lease_token);

    await expect(
      repo.markReady(first!.capture_photo_id, first!.lease_token!, {
        stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
        exportFileName: '0001_p1.jpg',
        sizeBytes: 12,
        sha256: VALID_SHA,
      }),
    ).rejects.toBeInstanceOf(ExportPrepFenceError);

    // Advance second worker to VALIDATING then READY
    await repo.markScanning(second!.capture_photo_id, second!.lease_token!, {
      stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
      exportFileName: '0001_p1.jpg',
      sizeBytes: 12,
    });
    await repo.markValidating(second!.capture_photo_id, second!.lease_token!);
    await repo.markReady(second!.capture_photo_id, second!.lease_token!, {
      stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
      exportFileName: '0001_p1.jpg',
      sizeBytes: 12,
      sha256: VALID_SHA,
    });
    expect(rows.get('p1')?.status).toBe('READY');
    expect(rows.get('p1')?.sha256).toBe(VALID_SHA);
  });

  it('concurrent claim: only one worker owns the lease', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    const [a, b] = await Promise.all([repo.claimNext('s1'), repo.claimNext('s1')]);
    const claimed = [a, b].filter(Boolean);
    expect(claimed).toHaveLength(1);
    expect(rows.get('p1')?.lease_token).toBe(claimed[0]!.lease_token);
  });

  it('markExcluded invalidates active lease so worker cannot READY', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    const job = await repo.claimNext('s1');
    await repo.markExcluded('p1');
    expect(rows.get('p1')?.status).toBe('EXCLUDED');
    expect(rows.get('p1')?.lease_token).toBeNull();
    await expect(
      repo.markScanning(job!.capture_photo_id, job!.lease_token!, {
        stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
        exportFileName: '0001_p1.jpg',
        sizeBytes: 12,
      }),
    ).rejects.toBeInstanceOf(ExportPrepFenceError);
  });

  it('rejects READY with invalid sha256', async () => {
    const { db } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    const job = await repo.claimNext('s1');
    await repo.markScanning(job!.capture_photo_id, job!.lease_token!, {
      stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
      exportFileName: '0001_p1.jpg',
      sizeBytes: 12,
    });
    await repo.markValidating(job!.capture_photo_id, job!.lease_token!);
    await expect(
      repo.markReady(job!.capture_photo_id, job!.lease_token!, {
        stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
        exportFileName: '0001_p1.jpg',
        sizeBytes: 12,
        sha256: 'meta-hash-not-hex',
      }),
    ).rejects.toThrow(/EXPORT_PREP_READY_INCOMPLETE/);
    expect(isValidStagedSha256('meta-hash-not-hex')).toBe(false);
  });

  it('markFailedFenced rejects mismatched lease', async () => {
    const { db } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    const job = await repo.claimNext('s1');
    await expect(
      repo.markFailedFenced(job!.capture_photo_id, 'wrong-token', 'X', 'y'),
    ).rejects.toBeInstanceOf(ExportPrepFenceError);
  });
});

describe('ExportPrepPhotoCoordinator', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  it('READY → EXCLUDED → reincorporate promotes to READY when staging valid', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    const job = await repo.claimNext('s1');
    await repo.markScanning(job!.capture_photo_id, job!.lease_token!, {
      stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
      exportFileName: '0001_p1.jpg',
      sizeBytes: 12,
    });
    await repo.markValidating(job!.capture_photo_id, job!.lease_token!);
    await repo.markReady(job!.capture_photo_id, job!.lease_token!, {
      stagingUri: 'file:///docs/export-staging/s1/photos/x.jpg',
      exportFileName: '0001_p1.jpg',
      sizeBytes: 12,
      sha256: VALID_SHA,
    });

    const wake = jest.fn();
    const coordinator = new ExportPrepPhotoCoordinator({
      capture: {
        exclude: jest.fn(async () => undefined),
        reincorporate: jest.fn(async () => undefined),
      } as never,
      prepQueue: { markPhotoExcluded: (id: string) => repo.markExcluded(id), wake } as never,
      prepRepo: repo,
      getSessionId: () => 's1',
      resolvePhotoIdByAssetId: async () => 'p1',
    });

    await coordinator.excludeByAssetId('asset-1');
    expect(rows.get('p1')?.status).toBe('EXCLUDED');

    await coordinator.reincorporateByAssetId('asset-1');
    expect(rows.get('p1')?.status).toBe('READY');
    expect(wake).not.toHaveBeenCalled();
  });

  it('reincorporate without staging wakes queue (QUEUED)', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    await repo.markExcluded('p1');
    rows.set('p1', {
      ...rows.get('p1')!,
      staging_uri: 'file:///docs/missing.jpg',
      sha256: null,
      size_bytes: null,
    });

    const wake = jest.fn();
    const coordinator = new ExportPrepPhotoCoordinator({
      capture: {
        exclude: jest.fn(async () => undefined),
        reincorporate: jest.fn(async () => undefined),
      } as never,
      prepQueue: { markPhotoExcluded: (id: string) => repo.markExcluded(id), wake } as never,
      prepRepo: repo,
      getSessionId: () => 's1',
      resolvePhotoIdByAssetId: async () => 'p1',
    });

    await coordinator.reincorporateByAssetId('a');
    expect(rows.get('p1')?.status).toBe('QUEUED');
    expect(wake).toHaveBeenCalled();
  });

  it('propagates capture exclude failure', async () => {
    const { db } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    const coordinator = new ExportPrepPhotoCoordinator({
      capture: {
        exclude: jest.fn(async () => {
          throw new Error('capture exclude failed');
        }),
        reincorporate: jest.fn(async () => undefined),
      } as never,
      prepQueue: { markPhotoExcluded: jest.fn(), wake: jest.fn() } as never,
      prepRepo: repo,
      getSessionId: () => 's1',
      resolvePhotoIdByAssetId: async () => 'p1',
    });
    await expect(coordinator.excludeByAssetId('a')).rejects.toThrow(/capture exclude failed/);
  });
});

describe('ensureJobsForEligiblePhotos + barrier', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  it('backfills historical session without jobs (idempotent)', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    const photos = [
      {
        id: 'p1',
        capture_session_id: 's1',
        status: 'stable',
        uri: 'file://source/1.jpg',
        size: 10,
        width: 1,
        height: 1,
        sequence_number: 1,
        display_name: '1.jpg',
      },
      {
        id: 'p2',
        capture_session_id: 's1',
        status: 'excluded',
        uri: 'file://source/2.jpg',
        size: 10,
        width: 1,
        height: 1,
        sequence_number: 2,
        display_name: '2.jpg',
      },
    ];
    const queue = new ExportPrepQueue({
      prepRepo: repo,
      captureRepo: {
        getSession: async () => ({ id: 's1', active_freeze_id: null }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async (id: string) => photos.find((p) => p.id === id) ?? null,
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });

    const a = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'RECOVERY' });
    const b = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'RECOVERY' });
    expect(a.createdJobs).toBe(1);
    expect(a.eligiblePhotos).toBe(1);
    expect(b.createdJobs).toBe(0);
    expect(b.existingJobs).toBeGreaterThanOrEqual(1);
    expect(rows.has('p1')).toBe(true);
    expect(rows.has('p2')).toBe(false);

    const gate = await queue.evaluateExportability('s1');
    expect(gate.totalEligible).toBe(1);
    expect(gate.missingJobs).toBe(0);
    expect(gate.pending).toBe(1);
    expect(gate.ok).toBe(false);
  });

  it('invalidates READY with missing staging', async () => {
    const { db, rows } = createMemoryExportPrepDb();
    const repo = new ExportPrepRepository(db as never);
    await repo.enqueueIdempotent({
      capturePhotoId: 'p1',
      captureSessionId: 's1',
      sourceUri: 'file://source/a.jpg',
      sourceFingerprint: null,
      exportFileName: '0001_p1.jpg',
    });
    const job = await repo.claimNext('s1');
    await repo.markScanning(job!.capture_photo_id, job!.lease_token!, {
      stagingUri: 'file:///docs/export-staging/missing.jpg',
      exportFileName: '0001_p1.jpg',
      sizeBytes: 12,
    });
    await repo.markValidating(job!.capture_photo_id, job!.lease_token!);
    // Force READY with missing uri bypassing exists check at mark time
    rows.set('p1', {
      ...rows.get('p1')!,
      status: 'READY',
      lease_token: null,
      staging_uri: 'file:///docs/export-staging/missing.jpg',
      sha256: VALID_SHA,
      size_bytes: 12,
      export_file_name: '0001_p1.jpg',
    });

    const queue = new ExportPrepQueue({
      prepRepo: repo,
      captureRepo: {
        getSession: async () => ({ id: 's1', active_freeze_id: null }),
        listPhotos: async () => [
          {
            id: 'p1',
            capture_session_id: 's1',
            status: 'stable',
            uri: 'file://source/a.jpg',
            size: 10,
            width: 1,
            height: 1,
            sequence_number: 1,
            display_name: 'a.jpg',
          },
        ],
        listFreezePhotos: async () => [],
        getPhotoById: async () => null,
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });

    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'EXPORT_PREFLIGHT' });
    expect(result.invalidatedReadyJobs).toBe(1);
    expect(result.requeuedJobs).toBe(1);
    // invalidateReady → FAILED_RETRYABLE, then enqueueIdempotent requeues to QUEUED (attempt preserved).
    expect(rows.get('p1')?.status).toBe('QUEUED');
    expect(rows.get('p1')?.staging_uri).toBeNull();
    expect(rows.get('p1')?.sha256).toBeNull();
  });
});

describe('upload policy independence (enqueue path)', () => {
  it.each(['MANUAL', 'NOW', 'WHEN_CONNECTED'] as const)(
    'enqueueStablePhoto works for policy %s',
    async (policy) => {
      void policy;
      const { db, rows } = createMemoryExportPrepDb();
      const repo = new ExportPrepRepository(db as never);
      const photo = {
        id: 'p1',
        capture_session_id: 's1',
        status: 'stable',
        uri: 'file://source/a.jpg',
        size: 10,
        width: 1,
        height: 1,
        sequence_number: 1,
        display_name: 'a.jpg',
      };
      const queue = new ExportPrepQueue({
        prepRepo: repo,
        captureRepo: {
          getSession: async () => ({ id: 's1', upload_policy: policy, active_freeze_id: null }),
          getPhotoById: async () => photo,
          listPhotos: async () => [photo],
          listFreezePhotos: async () => [],
        } as never,
        draftRepo: { listForSession: async () => [] } as never,
        localCodeScan: null,
        localCodeScanEnabled: false,
      });
      await queue.enqueueStablePhoto('s1', 'p1');
      expect(rows.get('p1')?.status).toBe('QUEUED');
    },
  );

  it.each(['uploading', 'upload_review'] as const)(
    'enqueueStablePhoto works for session status %s',
    async (status) => {
      const { db, rows } = createMemoryExportPrepDb();
      const repo = new ExportPrepRepository(db as never);
      const photo = {
        id: 'p1',
        capture_session_id: 's1',
        status: 'stable',
        uri: 'file://source/a.jpg',
        size: 10,
        width: 1,
        height: 1,
        sequence_number: 1,
        display_name: 'a.jpg',
      };
      const queue = new ExportPrepQueue({
        prepRepo: repo,
        captureRepo: {
          getSession: async () => ({ id: 's1', status, upload_policy: 'MANUAL', active_freeze_id: null }),
          getPhotoById: async () => photo,
          listPhotos: async () => [photo],
          listFreezePhotos: async () => [],
        } as never,
        draftRepo: { listForSession: async () => [] } as never,
        localCodeScan: null,
        localCodeScanEnabled: false,
      });
      await queue.enqueueStablePhoto('s1', 'p1');
      expect(rows.get('p1')?.status).toBe('QUEUED');
    },
  );
});
