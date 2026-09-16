/**
 * Phase 2: producers independent of upload policy + idempotent historical backfill.
 */

import {
  selectEligibleExportPrepPhotos,
  selectExportPackagingPhotos,
  selectNonProcessableExportPhotos,
} from '../src/features/exportPrep/eligibleExportPhotos';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { ExportPrepRepository } from '../src/database/repositories/exportPrepRepository';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';
import { resolveFeatureFlags, DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';
import { MIGRATIONS } from '../src/database/migrations/migrations';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async (uri: string) => {
    if (String(uri).includes('missing')) return { exists: false };
    return { exists: true, size: 12, modificationTime: Date.now() / 1000 };
  }),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello-staged').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(async () => 'c'.repeat(64)),
}));

const VALID_SHA = 'c'.repeat(64);

type Row = Record<string, unknown> & {
  capture_photo_id: string;
  capture_session_id: string;
  status: string;
  attempt_count: number;
  lease_token: string | null;
  lease_expires_at: string | null;
  staging_uri: string | null;
  sha256: string | null;
  size_bytes: number | null;
  export_file_name: string | null;
  queued_at: string;
};

/** Minimal Map-backed SQLite stand-in (same shape as fencing suite). */
function createMemoryDb() {
  const rows = new Map<string, Row>();
  const db = {
    execAsync: async () => undefined,
    getFirstAsync: async <T,>(sql: string, ...params: unknown[]): Promise<T | null> => {
      if (sql.includes('WHERE capture_photo_id = ?') && !sql.includes('ORDER BY')) {
        return (rows.get(String(params[0])) as T) ?? null;
      }
      return null;
    },
    getAllAsync: async <T,>(sql: string, ...params: unknown[]): Promise<T[]> => {
      if (sql.includes('GROUP BY status')) {
        const sid = String(params[0]);
        const counts = new Map<string, number>();
        for (const r of rows.values()) {
          if (r.capture_session_id !== sid) continue;
          counts.set(r.status, (counts.get(r.status) ?? 0) + 1);
        }
        return [...counts.entries()].map(([status, c]) => ({ status, c }) as T);
      }
      if (sql.includes('WHERE capture_session_id = ?')) {
        return [...rows.values()].filter((r) => r.capture_session_id === String(params[0])) as T[];
      }
      return [];
    },
    runAsync: async (sql: string, ...p: unknown[]) => {
      if (sql.includes('INSERT INTO export_prep_jobs')) {
        const id = String(p[0]);
        rows.set(id, {
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
        } as Row);
        return { changes: 1, lastInsertRowId: 1 };
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
      if (
        sql.includes("status = 'QUEUED'") &&
        sql.includes('source_uri = ?') &&
        sql.includes('lease_token IS')
      ) {
        const id = String(p[4]);
        const observedStatus = String(p[5]);
        const observedToken = p[6] as string | null;
        const now = String(p[7]);
        const cur = rows.get(id);
        if (!cur || cur.status !== observedStatus) return { changes: 0, lastInsertRowId: 0 };
        const tokenMatch =
          (observedToken == null && cur.lease_token == null) ||
          cur.lease_token === observedToken;
        const expiredOrNull =
          cur.lease_token == null ||
          cur.lease_expires_at == null ||
          cur.lease_expires_at < now;
        if (!(tokenMatch && expiredOrNull)) return { changes: 0, lastInsertRowId: 0 };
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
      if (
        sql.includes("status = 'QUEUED'") &&
        sql.includes('source_uri = ?') &&
        sql.includes("status = 'FAILED_RETRYABLE'")
      ) {
        const id = String(p[4]);
        const cur = rows.get(id);
        if (!cur || cur.status !== 'FAILED_RETRYABLE') return { changes: 0, lastInsertRowId: 0 };
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
      return { changes: 0, lastInsertRowId: 0 };
    },
  };
  return { db, rows };
}

function photo(partial: { id: string; status: string; sequence_number?: number }) {
  return {
    id: partial.id,
    capture_session_id: 's1',
    status: partial.status,
    uri: 'file://source/' + partial.id + '.jpg',
    size: 10,
    width: 1,
    height: 1,
    sequence_number: partial.sequence_number ?? 1,
    display_name: partial.id + '.jpg',
  };
}

describe('eligibleExportPhotos canonical selectors', () => {
  it('separates processable stables from excluded/rejected', () => {
    const photos = [
      photo({ id: 'a', status: 'stable' }),
      photo({ id: 'b', status: 'excluded' }),
      photo({ id: 'c', status: 'rejected' }),
      photo({ id: 'd', status: 'waiting' }),
    ] as never[];
    expect(selectEligibleExportPrepPhotos(photos).map((p) => p.id)).toEqual(['a']);
    expect(selectNonProcessableExportPhotos(photos).map((p) => p.id)).toEqual(['b', 'c']);
    expect(selectExportPackagingPhotos(photos).map((p) => p.id)).toEqual(['a', 'd']);
  });
});

describe('Phase 2 feature flag rollout', () => {
  it('DEFAULT on (non-prod); production opt-in; kill-switch works', () => {
    expect(DEFAULT_FEATURE_FLAGS.mobileExportPrepQueue).toBe(true);
    expect(resolveFeatureFlags({}, 'production').mobileExportPrepQueue).toBe(false);
    expect(resolveFeatureFlags({}, 'development').mobileExportPrepQueue).toBe(true);
    expect(resolveFeatureFlags({ mobileExportPrepQueue: '0' }, 'staging').mobileExportPrepQueue).toBe(
      false,
    );
  });
});

describe('Phase 2 migration presence (v34→v35 additive)', () => {
  it('v35 creates export_prep_jobs without rewriting prior tables', () => {
    const versions = MIGRATIONS.map((m) => m.version);
    expect(versions).toContain(34);
    expect(versions).toContain(35);
    const v35 = MIGRATIONS.find((m) => m.version === 35)!;
    expect(v35.sql).toContain('CREATE TABLE IF NOT EXISTS export_prep_jobs');
    expect(v35.sql).not.toContain('DROP TABLE');
    const v34 = MIGRATIONS.find((m) => m.version === 34)!;
    expect(v34.sql).not.toContain('export_prep_jobs');
  });
});

describe('Phase 2 producers + backfill persistence', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  function makeQueue(photos: ReturnType<typeof photo>[], rows: Map<string, Row>, db: unknown) {
    const repo = new ExportPrepRepository(db as never);
    const queue = new ExportPrepQueue({
      prepRepo: repo,
      captureRepo: {
        getSession: async () => ({ id: 's1', active_freeze_id: null, upload_policy: 'MANUAL' }),
        listPhotos: async () => photos,
        listFreezePhotos: async () => photos,
        getPhotoById: async (id: string) => photos.find((p) => p.id === id) ?? null,
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    return { queue, repo, rows };
  }

  it('enqueueStablePhoto is idempotent (unit; policy wiring covered in photoStableProducers)', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [photo({ id: 'p1', status: 'stable' })];
    const { queue } = makeQueue(photos, rows, db);
    await queue.enqueueStablePhoto('s1', 'p1');
    await queue.enqueueStablePhoto('s1', 'p1');
    expect(rows.size).toBe(1);
    expect(rows.get('p1')?.status).toBe('QUEUED');
  });

  it('counts missing/unreadable sources without reporting full success', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [
      photo({ id: 'ok', status: 'stable' }),
      { ...photo({ id: 'gone', status: 'stable' }), uri: 'file://missing/gone.jpg' },
    ];
    const { queue } = makeQueue(photos, rows, db);
    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'FINISH' });
    expect(result.createdJobs).toBe(1);
    expect(result.missingSourcePhotos).toBe(1);
    expect(result.partialErrors.some((e) => e.includes('missing_source:gone'))).toBe(true);
    expect(rows.has('gone')).toBe(false);
  });

  it('backfill historical session creates jobs; second pass is idempotent', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [
      photo({ id: 'p1', status: 'stable', sequence_number: 1 }),
      photo({ id: 'p2', status: 'stable', sequence_number: 2 }),
      photo({ id: 'p3', status: 'excluded' }),
    ];
    const { queue } = makeQueue(photos, rows, db);
    const first = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'REVIEW_OPEN' });
    expect(first.createdJobs).toBe(2);
    expect(first.eligiblePhotos).toBe(2);
    expect(first.reason).toBe('REVIEW_OPEN');
    const second = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'EXPORT_PREFLIGHT' });
    expect(second.createdJobs).toBe(0);
    expect(second.existingJobs).toBeGreaterThanOrEqual(2);
    expect(rows.size).toBe(2);
  });

  it('preserves FAILED_TERMINAL and FAILED_RETRYABLE attempt_count', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [
      photo({ id: 'term', status: 'stable' }),
      photo({ id: 'retry', status: 'stable' }),
    ];
    const { queue, repo } = makeQueue(photos, rows, db);
    await queue.ensureJobsForEligiblePhotos('s1', { reason: 'RECOVERY' });
    rows.set('term', {
      ...rows.get('term')!,
      status: 'FAILED_TERMINAL',
      attempt_count: 3,
    });
    rows.set('retry', {
      ...rows.get('retry')!,
      status: 'FAILED_RETRYABLE',
      attempt_count: 2,
    });
    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'FINISH' });
    expect(result.createdJobs).toBe(0);
    expect(rows.get('term')?.status).toBe('FAILED_TERMINAL');
    expect(rows.get('term')?.attempt_count).toBe(3);
    expect(rows.get('retry')?.status).toBe('FAILED_RETRYABLE');
    expect(rows.get('retry')?.attempt_count).toBe(2);
    // claim path still sees retryable
    expect((await repo.getByPhotoId('retry'))?.attempt_count).toBe(2);
  });

  it('does not interfere with in-flight lease', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [photo({ id: 'p1', status: 'stable' })];
    const { queue } = makeQueue(photos, rows, db);
    await queue.ensureJobsForEligiblePhotos('s1', { reason: 'RECOVERY' });
    rows.set('p1', {
      ...rows.get('p1')!,
      status: 'SCANNING',
      lease_token: 'live-lease',
      lease_expires_at: '2099-01-01T00:00:00.000Z',
      attempt_count: 1,
    });
    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'REVIEW_OPEN' });
    expect(result.createdJobs).toBe(0);
    expect(result.requeuedJobs).toBe(0);
    expect(rows.get('p1')?.lease_token).toBe('live-lease');
    expect(rows.get('p1')?.status).toBe('SCANNING');
  });

  it('keeps READY with valid staging; invalidates READY missing staging', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [
      photo({ id: 'ok', status: 'stable' }),
      photo({ id: 'bad', status: 'stable' }),
    ];
    const { queue } = makeQueue(photos, rows, db);
    await queue.ensureJobsForEligiblePhotos('s1', { reason: 'RECOVERY' });
    rows.set('ok', {
      ...rows.get('ok')!,
      status: 'READY',
      staging_uri: 'file:///docs/export-staging/s1/photos/ok.jpg',
      sha256: VALID_SHA,
      size_bytes: 12,
      export_file_name: '0001_ok.jpg',
    });
    rows.set('bad', {
      ...rows.get('bad')!,
      status: 'READY',
      staging_uri: 'file:///docs/export-staging/missing.jpg',
      sha256: VALID_SHA,
      size_bytes: 12,
      export_file_name: '0001_bad.jpg',
    });
    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'EXPORT_PREFLIGHT' });
    expect(result.invalidatedReadyJobs).toBe(1);
    expect(rows.get('ok')?.status).toBe('READY');
    expect(rows.get('bad')?.status).toBe('QUEUED');
  });

  it('excludes capture-excluded photos without creating processable jobs', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [photo({ id: 'p1', status: 'excluded' })];
    const { queue } = makeQueue(photos, rows, db);
    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'FINISH' });
    expect(result.createdJobs).toBe(0);
    expect(result.eligiblePhotos).toBe(0);
    expect(rows.size).toBe(0);
  });

  it('freeze set is used when active_freeze_id is set', async () => {
    const { db, rows } = createMemoryDb();
    const sessionPhotos = [
      photo({ id: 'old', status: 'stable' }),
      photo({ id: 'new', status: 'stable' }),
    ];
    const freezePhotos = [photo({ id: 'old', status: 'stable' })];
    const repo = new ExportPrepRepository(db as never);
    const queue = new ExportPrepQueue({
      prepRepo: repo,
      captureRepo: {
        getSession: async () => ({ id: 's1', active_freeze_id: 'freeze-1' }),
        listPhotos: async () => sessionPhotos,
        listFreezePhotos: async () => freezePhotos,
        getPhotoById: async () => null,
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
    });
    const result = await queue.ensureJobsForEligiblePhotos('s1', { reason: 'FINISH' });
    expect(result.createdJobs).toBe(1);
    expect(rows.has('old')).toBe(true);
    expect(rows.has('new')).toBe(false);
  });

  it('concurrent backfill does not duplicate rows', async () => {
    const { db, rows } = createMemoryDb();
    const photos = [photo({ id: 'p1', status: 'stable' })];
    const { queue } = makeQueue(photos, rows, db);
    await Promise.all([
      queue.ensureJobsForEligiblePhotos('s1', { reason: 'REVIEW_OPEN' }),
      queue.ensureJobsForEligiblePhotos('s1', { reason: 'EXPORT_PREFLIGHT' }),
    ]);
    expect(rows.size).toBe(1);
  });
});
