/**
 * Phase 6: integrity, cleanup, retention, path safety, reconcile, purge.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { MIGRATIONS } from '../src/database/migrations/migrations';
import { LocalExportAttemptRepository } from '../src/database/repositories/localExportAttemptRepository';
import { LocalCsvExportRepository } from '../src/database/repositories/localCsvExportRepository';
import { ExportPrepRepository } from '../src/database/repositories/exportPrepRepository';
import {
  assessStorageSpace,
  decideArtifactRetention,
  DEFAULT_ARTIFACT_RETENTION_TTLS,
  isActiveExportAttemptState,
} from '../src/features/exportPrep/artifactRetentionPolicy';
import {
  assertSafeSandboxDeleteTarget,
  UnsafeSandboxPathError,
} from '../src/features/exportPrep/safeSandboxPath';
import { cleanupOutcomeLabel, emptyCleanupResult } from '../src/features/exportPrep/cleanupTypes';
import { ExportArtifactReconciler } from '../src/features/exportPrep/exportArtifactReconciler';
import { SessionArtifactPurgeCoordinator } from '../src/features/exportPrep/sessionArtifactPurgeCoordinator';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';

const DOC = 'file:///app/docs/';
const CACHE = 'file:///app/cache/';

const fsState = {
  files: new Map<string, { size: number; mtimeSec: number }>(),
  dirs: new Set<string>(),
};

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///app/docs/',
  cacheDirectory: 'file:///app/cache/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async (uri: string) => {
    const n = String(uri);
    if (fsState.dirs.has(n) || fsState.dirs.has(n.endsWith('/') ? n : `${n}/`)) {
      return { exists: true, isDirectory: true, modificationTime: Date.now() / 1000 };
    }
    const f = fsState.files.get(n);
    if (!f) return { exists: false };
    return { exists: true, size: f.size, modificationTime: f.mtimeSec };
  }),
  makeDirectoryAsync: jest.fn(async (uri: string) => {
    fsState.dirs.add(uri.endsWith('/') ? uri : `${uri}/`);
  }),
  readDirectoryAsync: jest.fn(async (uri: string) => {
    const prefix = uri.endsWith('/') ? uri : `${uri}/`;
    const names = new Set<string>();
    for (const key of fsState.files.keys()) {
      if (key.startsWith(prefix)) {
        const rest = key.slice(prefix.length);
        const name = rest.split('/')[0];
        if (name) names.add(name);
      }
    }
    for (const d of fsState.dirs) {
      if (d.startsWith(prefix)) {
        const rest = d.slice(prefix.length);
        const name = rest.split('/').filter(Boolean)[0];
        if (name) names.add(name);
      }
    }
    return [...names];
  }),
  deleteAsync: jest.fn(async (uri: string) => {
    fsState.files.delete(uri);
    fsState.dirs.delete(uri);
    fsState.dirs.delete(uri.endsWith('/') ? uri : `${uri}/`);
  }),
  moveAsync: jest.fn(async ({ from, to }: { from: string; to: string }) => {
    const f = fsState.files.get(from);
    if (f) {
      fsState.files.set(to, f);
      fsState.files.delete(from);
    }
  }),
  copyAsync: jest.fn(async () => undefined),
  getFreeDiskStorageAsync: jest.fn(async () => 2 * 1024 * 1024 * 1024),
  getTotalDiskCapacityAsync: jest.fn(async () => 64 * 1024 * 1024 * 1024),
}));

type AsyncDb = {
  execAsync(sql: string): Promise<void>;
  runAsync(sql: string, ...params: unknown[]): Promise<{ changes: number; lastInsertRowId: number }>;
  getFirstAsync<T>(sql: string, ...params: unknown[]): Promise<T | null>;
  getAllAsync<T>(sql: string, ...params: unknown[]): Promise<T[]>;
  close(): void;
};

function wrapDatabaseSync(sync: DatabaseSync): AsyncDb {
  return {
    async execAsync(sql: string) {
      sync.exec(sql);
    },
    async runAsync(sql: string, ...params: unknown[]) {
      const stmt = sync.prepare(sql);
      const result = stmt.run(...(params as never[]));
      stmt.finalize?.();
      return {
        changes: Number(result.changes ?? 0),
        lastInsertRowId: Number(result.lastInsertRowid ?? 0),
      };
    },
    async getFirstAsync<T>(sql: string, ...params: unknown[]) {
      const stmt = sync.prepare(sql);
      const row = (stmt.get(...(params as never[])) as T) ?? null;
      stmt.finalize?.();
      return row;
    },
    async getAllAsync<T>(sql: string, ...params: unknown[]) {
      const stmt = sync.prepare(sql);
      const rows = stmt.all(...(params as never[])) as T[];
      stmt.finalize?.();
      return rows;
    },
    close() {
      sync.close();
    },
  };
}

function applyMigrationSql(sync: DatabaseSync, sql: string): void {
  for (const chunk of sql.split(';')) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;
    sync.exec(`${trimmed};`);
  }
}

function openTempDb(): { db: AsyncDb; filePath: string; sync: DatabaseSync } {
  const filePath = path.join(
    os.tmpdir(),
    `phase6-${Date.now()}-${Math.random().toString(16).slice(2)}.db`,
  );
  const sync = new DatabaseSync(filePath);
  sync.exec('PRAGMA foreign_keys = ON;');
  for (const m of MIGRATIONS) {
    applyMigrationSql(sync, m.sql);
  }
  return { db: wrapDatabaseSync(sync), filePath, sync };
}

function putFile(uri: string, size: number, ageMs: number) {
  fsState.files.set(uri, {
    size,
    mtimeSec: (Date.now() - ageMs) / 1000,
  });
}

beforeEach(() => {
  fsState.files.clear();
  fsState.dirs.clear();
  __resetSqliteWriteGateForTests();
});

describe('Phase 6 safeSandboxPath', () => {
  const roots = { documentDirectory: DOC, cacheDirectory: CACHE };

  it('rejects MediaStore / content URIs', () => {
    expect(() =>
      assertSafeSandboxDeleteTarget('content://media/external/images/1', roots),
    ).toThrow(UnsafeSandboxPathError);
  });

  it('rejects path traversal', () => {
    expect(() =>
      assertSafeSandboxDeleteTarget(`${DOC}export-staging/../Secrets`, roots),
    ).toThrow(UnsafeSandboxPathError);
  });

  it('rejects outside sandbox', () => {
    expect(() => assertSafeSandboxDeleteTarget('/tmp/evil.zip', roots)).toThrow(
      UnsafeSandboxPathError,
    );
  });

  it('rejects artifact root deletion', () => {
    expect(() =>
      assertSafeSandboxDeleteTarget(`${DOC}aisle-exports/`, roots),
    ).toThrow(UnsafeSandboxPathError);
  });

  it('allows aisle-exports file under sandbox', () => {
    const r = assertSafeSandboxDeleteTarget(`${DOC}aisle-exports/a.tmp.zip`, roots);
    expect(r.rootKind).toBe('document');
  });

  it('allows session staging dir when opted in', () => {
    const r = assertSafeSandboxDeleteTarget(`${DOC}export-staging/sess-1/`, roots, {
      allowedPrefixes: ['export-staging/'],
      allowSessionDirDelete: true,
    });
    expect(r.rootKind).toBe('document');
  });
});

describe('Phase 6 retention policy', () => {
  it('never auto-deletes MediaStore originals', () => {
    const d = decideArtifactRetention({
      artifactClass: 'original_mediastore',
      ageMs: 999 * 24 * 60 * 60 * 1000,
      sessionPurgeRequested: true,
    });
    expect(d.action).toBe('never_auto_delete');
  });

  it('keeps READY staging even when flag is off', () => {
    const d = decideArtifactRetention({
      artifactClass: 'staging_ready',
      ageMs: 999 * 24 * 60 * 60 * 1000,
      exportPrepFlagEnabled: false,
    });
    expect(d.action).toBe('keep');
  });

  it('keeps active attempt temps', () => {
    const d = decideArtifactRetention({
      artifactClass: 'zip_temp',
      ageMs: DEFAULT_ARTIFACT_RETENTION_TTLS.zipTempMs + 1,
      hasActiveLeaseOrAttempt: true,
    });
    expect(d.action).toBe('keep');
  });

  it('cleans expired temps without active attempt', () => {
    const d = decideArtifactRetention({
      artifactClass: 'zip_temp',
      ageMs: DEFAULT_ARTIFACT_RETENTION_TTLS.zipTempMs + 1,
      hasActiveLeaseOrAttempt: false,
    });
    expect(d.action).toBe('cleanup_safe');
  });

  it('keeps COMPLETE zip finals', () => {
    const d = decideArtifactRetention({
      artifactClass: 'zip_final',
      ageMs: 999 * 24 * 60 * 60 * 1000,
      referencedByCompleteExport: true,
    });
    expect(d.action).toBe('keep');
  });

  it('quarantines orphan finals after TTL', () => {
    const d = decideArtifactRetention({
      artifactClass: 'orphan_final',
      ageMs: DEFAULT_ARTIFACT_RETENTION_TTLS.orphanFinalMs + 1,
      referencedByCompleteExport: false,
    });
    expect(d.action).toBe('quarantine');
  });

  it('share cancel policy: finals stay keep (not purge)', () => {
    // Cancelling share must not request session purge — retention stays keep.
    const d = decideArtifactRetention({
      artifactClass: 'zip_final',
      ageMs: 60_000,
      referencedByCompleteExport: true,
      sessionPurgeRequested: false,
    });
    expect(d.action).toBe('keep');
  });

  it('assessStorageSpace distinguishes insufficient vs warning', () => {
    const low = assessStorageSpace({
      freeBytes: 100 * 1024 * 1024,
      estimatedPayloadBytes: 200 * 1024 * 1024,
    });
    expect(low.level).toBe('INSUFFICIENT_FOR_OPERATION');
    const warn = assessStorageSpace({
      freeBytes: 400 * 1024 * 1024,
      estimatedPayloadBytes: 1024,
    });
    expect(warn.level).toBe('LOW_SPACE_WARNING');
    const ok = assessStorageSpace({
      freeBytes: 2 * 1024 * 1024 * 1024,
      estimatedPayloadBytes: 10 * 1024 * 1024,
    });
    expect(ok.level).toBe('OK');
    const unk = assessStorageSpace({ freeBytes: null, estimatedPayloadBytes: 1 });
    expect(unk.level).toBe('UNKNOWN');
  });
});

describe('Phase 6 cleanup result semantics', () => {
  it('reports partial when some deletes fail', () => {
    const r = {
      ...emptyCleanupResult(Date.now() - 10),
      deleted: 2,
      failed: 1,
      errors: [
        {
          code: 'X',
          artifactType: 'zip_temp' as const,
          operation: 'delete',
          recoverable: true,
        },
      ],
    };
    expect(cleanupOutcomeLabel(r)).toBe('partial');
  });

  it('does not report completed when only failures', () => {
    const r = {
      ...emptyCleanupResult(Date.now() - 10),
      failed: 3,
      errors: [],
    };
    expect(cleanupOutcomeLabel(r)).toBe('failed');
  });
});

describe('Phase 6 local_export_attempts + reconcile (sqlite + fs)', () => {
  let db: AsyncDb;
  let filePath: string;

  beforeEach(() => {
    const opened = openTempDb();
    db = opened.db;
    filePath = opened.filePath;
  });

  afterEach(() => {
    db.close();
    try {
      fs.unlinkSync(filePath);
    } catch {
      // ignore
    }
  });

  async function seedSession(sessionId: string) {
    const now = new Date().toISOString();
    await db.runAsync(
      `INSERT INTO capture_sessions (
         id, inventory_id, inventory_name, aisle_id, aisle_name, status,
         started_at, scan_cursor_date_added, scan_cursor_asset_id,
         last_valid_cursor_date_added, last_valid_cursor_asset_id,
         created_at, updated_at
       ) VALUES (?, 'inv', 'Inv', 'aisle', 'Aisle', 'review', ?, 0, '', 0, '', ?, ?);`,
      sessionId,
      now,
      now,
      now,
    );
  }

  it('migration creates attempts table with state check', async () => {
    const row = await db.getFirstAsync<{ name: string }>(
      `SELECT name FROM sqlite_master WHERE type='table' AND name='local_export_attempts';`,
    );
    expect(row?.name).toBe('local_export_attempts');
  });

  it('keeps active temp; deletes expired temp without attempt', async () => {
    await seedSession('s-active');
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const exportRepo = new LocalCsvExportRepository(db as never);
    const now = new Date().toISOString();
    const activeTmp = `${DOC}aisle-exports/active.tmp.zip`;
    const staleTmp = `${DOC}aisle-exports/stale.tmp.zip`;
    fsState.dirs.add(`${DOC}aisle-exports/`);
    putFile(activeTmp, 100, 60_000);
    putFile(staleTmp, 200, DEFAULT_ARTIFACT_RETENTION_TTLS.zipTempMs + 60_000);

    await attemptRepo.insert({
      id: 'att-1',
      capture_session_id: 's-active',
      freeze_id: null,
      freeze_generation: null,
      content_fingerprint: null,
      state: 'WRITING',
      tmp_csv_uri: null,
      tmp_zip_uri: activeTmp,
      final_csv_uri: null,
      final_zip_uri: null,
      started_at: now,
      heartbeat_at: now,
      completed_at: null,
      error_code: null,
      created_at: now,
      updated_at: now,
    });

    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async () => null } as never,
      exportRepo,
      attemptRepo,
      prepRepo: null,
      logger: null,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });

    const result = await reconciler.runBounded({ maxFiles: 50, maxDurationMs: 5_000 });
    expect(fsState.files.has(activeTmp)).toBe(true);
    expect(fsState.files.has(staleTmp)).toBe(false);
    expect(result.deleted).toBeGreaterThanOrEqual(1);
    expect(result.skippedActive).toBeGreaterThanOrEqual(1);
  });

  it('quarantines orphan final without record after TTL', async () => {
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const exportRepo = new LocalCsvExportRepository(db as never);
    const orphan = `${DOC}aisle-exports/orphan-final.zip`;
    fsState.dirs.add(`${DOC}aisle-exports/`);
    fsState.dirs.add(`${DOC}export-quarantine/`);
    putFile(orphan, 50, DEFAULT_ARTIFACT_RETENTION_TTLS.orphanFinalMs + 1000);

    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async () => null } as never,
      exportRepo,
      attemptRepo,
      prepRepo: null,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    const result = await reconciler.runBounded({ maxFiles: 20, maxDurationMs: 5_000 });
    expect(result.quarantined).toBeGreaterThanOrEqual(1);
    expect(fsState.files.has(orphan)).toBe(false);
  });

  it('invalidates READY when staging missing', async () => {
    await seedSession('s-ready');
    const now = new Date().toISOString();
    await db.runAsync(
      `INSERT INTO capture_photos (
         id, capture_session_id, asset_id, uri, display_name, mime_type,
         size, width, height, date_added, date_modified, status,
         sequence_number, created_at, updated_at
       ) VALUES ('photo-1', 's-ready', 'a1', 'content://x', 'p.jpg', 'image/jpeg',
         1, 1, 1, 1, 1, 'stable', 1, ?, ?);`,
      now,
      now,
    );
    await db.runAsync(
      `INSERT INTO export_prep_jobs (
         capture_photo_id, capture_session_id, status, attempt_count, max_attempts,
         staging_uri, export_file_name, size_bytes, sha256,
         source_uri, source_fingerprint, queued_at, ready_at, created_at, updated_at
       ) VALUES ('photo-1', 's-ready', 'READY', 1, 5,
         ?, 'p.jpg', 10, ?,
         'content://x', 'fp', ?, ?, ?, ?);`,
      `${DOC}export-staging/s-ready/photos/missing.jpg`,
      'a'.repeat(64),
      now,
      now,
      now,
      now,
    );

    const prepRepo = new ExportPrepRepository(db as never);
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const exportRepo = new LocalCsvExportRepository(db as never);
    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async () => ({ id: 's-ready' }) } as never,
      exportRepo,
      attemptRepo,
      prepRepo,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    const result = await reconciler.runBounded({ maxFiles: 10, maxDurationMs: 5_000 });
    expect(result.invalidated).toBeGreaterThanOrEqual(1);
    const job = await prepRepo.getByPhotoId('photo-1');
    expect(job?.status).toBe('FAILED_RETRYABLE');
    expect(job?.error_code).toBe('STAGING_MISSING');
  });

  it('failStaleActive marks abandoned WRITING attempts FAILED', async () => {
    await seedSession('s-stale');
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const old = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    await attemptRepo.insert({
      id: 'stale-1',
      capture_session_id: 's-stale',
      freeze_id: null,
      freeze_generation: null,
      content_fingerprint: null,
      state: 'WRITING',
      tmp_csv_uri: null,
      tmp_zip_uri: `${DOC}aisle-exports/x.tmp.zip`,
      final_csv_uri: null,
      final_zip_uri: null,
      started_at: old,
      heartbeat_at: old,
      completed_at: null,
      error_code: null,
      created_at: old,
      updated_at: old,
    });
    const n = await attemptRepo.failStaleActive(15 * 60 * 1000);
    expect(n).toBe(1);
    const row = await attemptRepo.getById('stale-1');
    expect(row?.state).toBe('FAILED');
    expect(isActiveExportAttemptState(row!.state)).toBe(false);
  });

  it('purge session is idempotent and concurrent-safe', async () => {
    await seedSession('s-purge');
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const exportRepo = new LocalCsvExportRepository(db as never);
    const now = new Date().toISOString();
    const zip = `${DOC}aisle-exports/exp.1.zip`;
    const csv = `${DOC}aisle-exports/exp.1.csv`;
    putFile(zip, 10, 0);
    putFile(csv, 5, 0);
    await attemptRepo.insert({
      id: 'p-att',
      capture_session_id: 's-purge',
      freeze_id: null,
      freeze_generation: null,
      content_fingerprint: 'fp',
      state: 'COMPLETE',
      tmp_csv_uri: null,
      tmp_zip_uri: null,
      final_csv_uri: csv,
      final_zip_uri: zip,
      started_at: now,
      heartbeat_at: now,
      completed_at: now,
      error_code: null,
      created_at: now,
      updated_at: now,
    });
    await exportRepo.insert({
      id: 'row-1',
      export_id: 'exp',
      schema_version: '1',
      scope: 'aisle',
      capture_session_id: 's-purge',
      inventory_id: 'inv',
      aisle_id: 'aisle',
      row_count: 1,
      checksum_sha256: 'c'.repeat(64),
      content_fingerprint: 'fp',
      file_uri: csv,
      exported_at: now,
      shared_at: null,
      created_at: now,
      updated_at: now,
    });

    const purge = new SessionArtifactPurgeCoordinator({
      attemptRepo,
      exportRepo,
      exportPrepQueue: {
        cancelAndDrainSession: jest.fn(async () => undefined),
        purgeSessionArtifacts: jest.fn(async () => undefined),
      } as never,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });

    const [a, b] = await Promise.all([
      purge.purgeSession('s-purge'),
      purge.purgeSession('s-purge'),
    ]);
    const outcomes = [a, b];
    expect(outcomes.some((r) => r.skippedActive === 1 || r.deleted >= 1)).toBe(true);
    const again = await purge.purgeSession('s-purge');
    expect(again.failed).toBe(0);
    expect(fsState.files.has(zip)).toBe(false);
    expect(fsState.files.has(csv)).toBe(false);
    expect(await attemptRepo.listBySession('s-purge')).toEqual([]);
    expect(await exportRepo.listForSession('s-purge')).toEqual([]);
  });

  it('bootstrap reconcile does not start two concurrent runs', async () => {
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const exportRepo = new LocalCsvExportRepository(db as never);
    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async () => null } as never,
      exportRepo,
      attemptRepo,
      prepRepo: null,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    // Force long run by filling many files
    fsState.dirs.add(`${DOC}aisle-exports/`);
    for (let i = 0; i < 30; i += 1) {
      putFile(
        `${DOC}aisle-exports/t${i}.tmp.zip`,
        1,
        DEFAULT_ARTIFACT_RETENTION_TTLS.zipTempMs + 1,
      );
    }
    const p1 = reconciler.runBounded({ maxFiles: 100, maxDurationMs: 50 });
    const p2 = reconciler.runBounded({ maxFiles: 100, maxDurationMs: 50 });
    const [r1, r2] = await Promise.all([p1, p2]);
    const skipped = [r1, r2].filter((r) =>
      r.errors.some((e) => e.code === 'RECONCILE_ALREADY_RUNNING'),
    );
    expect(skipped.length).toBe(1);
  });

  it('share success / cancel do not purge finals via retention', () => {
    // Explicit product policy: shared_at set must not auto-delete.
    const sharedKeep = decideArtifactRetention({
      artifactClass: 'zip_final',
      ageMs: 0,
      referencedByCompleteExport: true,
      sessionPurgeRequested: false,
    });
    expect(sharedKeep.action).toBe('keep');
  });
});
