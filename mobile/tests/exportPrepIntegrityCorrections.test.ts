/**
 * Phase 6 corrections: durable zip_uri refs, CAS attempts, purge pending, no false orphan quarantine.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { MIGRATIONS } from '../src/database/migrations/migrations';
import {
  ExportAttemptTransitionError,
  LocalExportAttemptRepository,
} from '../src/database/repositories/localExportAttemptRepository';
import {
  deriveZipUriFromCsvUri,
  LocalCsvExportRepository,
} from '../src/database/repositories/localCsvExportRepository';
import { SessionPurgeTaskRepository } from '../src/database/repositories/sessionPurgeTaskRepository';
import { ExportArtifactReconciler } from '../src/features/exportPrep/exportArtifactReconciler';
import { SessionArtifactPurgeCoordinator } from '../src/features/exportPrep/sessionArtifactPurgeCoordinator';
import { DEFAULT_ARTIFACT_RETENTION_TTLS } from '../src/features/exportPrep/artifactRetentionPolicy';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';

const DOC = 'file:///app/docs/';
const CACHE = 'file:///app/cache/';

const fsState = {
  files: new Map<string, { size: number; mtimeSec: number }>(),
  dirs: new Set<string>(),
  failReadDir: false,
  failDelete: new Set<string>(),
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
    if (fsState.failReadDir) throw new Error('EACCES');
    const prefix = uri.endsWith('/') ? uri : `${uri}/`;
    const names = new Set<string>();
    for (const key of fsState.files.keys()) {
      if (key.startsWith(prefix)) {
        const name = key.slice(prefix.length).split('/')[0];
        if (name) names.add(name);
      }
    }
    return [...names];
  }),
  deleteAsync: jest.fn(async (uri: string) => {
    if (fsState.failDelete.has(uri)) throw new Error('EPERM');
    fsState.files.delete(uri);
  }),
  moveAsync: jest.fn(async ({ from, to }: { from: string; to: string }) => {
    const f = fsState.files.get(from);
    if (f) {
      fsState.files.set(to, f);
      fsState.files.delete(from);
    }
  }),
  copyAsync: jest.fn(async () => undefined),
  getFreeDiskStorageAsync: jest.fn(async () => 8 * 1024 * 1024 * 1024),
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

function openTempDb(): { db: AsyncDb; filePath: string } {
  const filePath = path.join(
    os.tmpdir(),
    `p6c-${Date.now()}-${Math.random().toString(16).slice(2)}.db`,
  );
  const sync = new DatabaseSync(filePath);
  sync.exec('PRAGMA foreign_keys = ON;');
  for (const m of MIGRATIONS) applyMigrationSql(sync, m.sql);
  return { db: wrapDatabaseSync(sync), filePath };
}

function putFile(uri: string, size: number, ageMs: number) {
  fsState.files.set(uri, { size, mtimeSec: (Date.now() - ageMs) / 1000 });
}

beforeEach(() => {
  fsState.files.clear();
  fsState.dirs.clear();
  fsState.failReadDir = false;
  fsState.failDelete.clear();
  __resetSqliteWriteGateForTests();
});

describe('Phase 6 corrections — durable zip refs + CAS + purge', () => {
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
      /* ignore */
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

  it('keeps ZIP for 201 COMPLETE exports (authoritative zip_uri, no LIMIT orphan)', async () => {
    await seedSession('s-many');
    const exportRepo = new LocalCsvExportRepository(db as never);
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    fsState.dirs.add(`${DOC}aisle-exports/`);
    const now = new Date().toISOString();
    for (let i = 0; i < 201; i += 1) {
      const csv = `${DOC}aisle-exports/exp${i}.tok.csv`;
      const zip = `${DOC}aisle-exports/exp${i}.tok.zip`;
      putFile(csv, 10, 0);
      putFile(zip, 20, DEFAULT_ARTIFACT_RETENTION_TTLS.orphanFinalMs + 5000);
      await exportRepo.insert({
        id: `id-${i}`,
        export_id: `exp${i}`,
        schema_version: '1',
        scope: 'aisle',
        capture_session_id: 's-many',
        inventory_id: 'inv',
        aisle_id: 'aisle',
        row_count: 1,
        checksum_sha256: 'a'.repeat(64),
        content_fingerprint: `fp-${i}`,
        file_uri: csv,
        zip_uri: zip,
        exported_at: now,
        shared_at: null,
        created_at: now,
        updated_at: now,
      });
    }
    // True orphan
    const orphan = `${DOC}aisle-exports/orphan.tok.zip`;
    putFile(orphan, 5, DEFAULT_ARTIFACT_RETENTION_TTLS.orphanFinalMs + 5000);

    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async (id: string) => (id === 's-many' ? { id } : null) } as never,
      exportRepo,
      attemptRepo,
      prepRepo: null,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    const result = await reconciler.runBounded({ maxFiles: 500, maxDurationMs: 30_000 });
    for (let i = 0; i < 201; i += 1) {
      expect(fsState.files.has(`${DOC}aisle-exports/exp${i}.tok.zip`)).toBe(true);
    }
    expect(fsState.files.has(orphan)).toBe(false);
    expect(result.quarantined).toBeGreaterThanOrEqual(1);
  });

  it('resolves historical export without zip_uri via derived pair', async () => {
    await seedSession('s-hist');
    const exportRepo = new LocalCsvExportRepository(db as never);
    const now = new Date().toISOString();
    const csv = `${DOC}aisle-exports/legacy.1.csv`;
    const zip = `${DOC}aisle-exports/legacy.1.zip`;
    await db.runAsync(
      `INSERT INTO local_csv_exports (
         id, export_id, schema_version, scope, capture_session_id, inventory_id, aisle_id,
         row_count, checksum_sha256, content_fingerprint, file_uri, exported_at, shared_at,
         created_at, updated_at
       ) VALUES ('h1','e1','1','aisle','s-hist','inv','aisle',1,?,?,?, ?, NULL, ?, ?);`,
      'b'.repeat(64),
      'fp-hist',
      csv,
      now,
      now,
      now,
    );
    expect(await exportRepo.isArtifactReferenced(zip)).toBe(true);
    expect(deriveZipUriFromCsvUri(csv)).toBe(zip);
  });

  it('CANCELLED and FAILED cannot advance; PUBLISHING only from VALIDATING', async () => {
    await seedSession('s-cas');
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const now = new Date().toISOString();
    await attemptRepo.insert({
      id: 'a1',
      capture_session_id: 's-cas',
      freeze_id: null,
      freeze_generation: null,
      content_fingerprint: null,
      state: 'CREATED',
      tmp_csv_uri: null,
      tmp_zip_uri: null,
      final_csv_uri: null,
      final_zip_uri: null,
      started_at: now,
      heartbeat_at: now,
      completed_at: null,
      error_code: null,
      created_at: now,
      updated_at: now,
    });
    await attemptRepo.transitionState('a1', 'WRITING');
    await attemptRepo.transitionState('a1', 'VALIDATING');
    await expect(attemptRepo.transitionState('a1', 'COMPLETE')).rejects.toBeInstanceOf(
      ExportAttemptTransitionError,
    );
    await attemptRepo.transitionState('a1', 'PUBLISHING', {
      final_csv_uri: `${DOC}aisle-exports/x.csv`,
      final_zip_uri: `${DOC}aisle-exports/x.zip`,
    });
    await attemptRepo.transitionState('a1', 'CANCELLED', {
      completed_at: now,
      error_code: 'CANCEL',
    });
    await expect(attemptRepo.transitionState('a1', 'VALIDATING')).rejects.toBeInstanceOf(
      ExportAttemptTransitionError,
    );
    await expect(attemptRepo.transitionState('a1', 'COMPLETE')).rejects.toBeInstanceOf(
      ExportAttemptTransitionError,
    );

    await attemptRepo.insert({
      id: 'a2',
      capture_session_id: 's-cas',
      freeze_id: null,
      freeze_generation: null,
      content_fingerprint: null,
      state: 'CREATED',
      tmp_csv_uri: null,
      tmp_zip_uri: null,
      final_csv_uri: null,
      final_zip_uri: null,
      started_at: now,
      heartbeat_at: now,
      completed_at: null,
      error_code: null,
      created_at: now,
      updated_at: now,
    });
    await attemptRepo.transitionState('a2', 'FAILED', {
      completed_at: now,
      error_code: 'X',
    });
    await expect(attemptRepo.transitionState('a2', 'WRITING')).rejects.toBeInstanceOf(
      ExportAttemptTransitionError,
    );
  });

  it('readDirectoryAsync failure yields partial/failed not empty success', async () => {
    const exportRepo = new LocalCsvExportRepository(db as never);
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    fsState.dirs.add(`${DOC}aisle-exports/`);
    fsState.failReadDir = true;
    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async () => null } as never,
      exportRepo,
      attemptRepo,
      prepRepo: null,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    const result = await reconciler.runBounded({ maxFiles: 10, maxDurationMs: 5_000 });
    expect(result.failed).toBeGreaterThan(0);
    expect(result.errors.some((e) => e.code.includes('READ_FAILED'))).toBe(true);
  });

  it('purge failure retains metadata and PURGE_PARTIAL for retry', async () => {
    await seedSession('s-purge');
    const exportRepo = new LocalCsvExportRepository(db as never);
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const purgeTaskRepo = new SessionPurgeTaskRepository(db as never);
    const now = new Date().toISOString();
    const zip = `${DOC}aisle-exports/keep.zip`;
    const csv = `${DOC}aisle-exports/keep.csv`;
    putFile(zip, 10, 0);
    putFile(csv, 5, 0);
    fsState.failDelete.add(zip);
    await exportRepo.insert({
      id: 'r1',
      export_id: 'e1',
      schema_version: '1',
      scope: 'aisle',
      capture_session_id: 's-purge',
      inventory_id: 'inv',
      aisle_id: 'aisle',
      row_count: 1,
      checksum_sha256: 'c'.repeat(64),
      content_fingerprint: 'fp',
      file_uri: csv,
      zip_uri: zip,
      exported_at: now,
      shared_at: null,
      created_at: now,
      updated_at: now,
    });
    const purge = new SessionArtifactPurgeCoordinator({
      attemptRepo,
      exportRepo,
      purgeTaskRepo,
      exportPrepQueue: {
        cancelAndDrainSession: jest.fn(async () => undefined),
        purgeSessionArtifacts: jest.fn(async () => undefined),
      } as never,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    const result = await purge.purgeSession('s-purge');
    expect(result.failed).toBeGreaterThan(0);
    expect(await exportRepo.listForSession('s-purge')).toHaveLength(1);
    const task = await purgeTaskRepo.get('s-purge');
    expect(task?.state).toBe('PURGE_PARTIAL');
    expect(purgeTaskRepo.parsePendingUris(task!).includes(zip)).toBe(true);

    fsState.failDelete.clear();
    const retry = await purge.purgeSession('s-purge');
    expect(retry.failed).toBe(0);
    expect(await exportRepo.listForSession('s-purge')).toHaveLength(0);
    expect((await purgeTaskRepo.get('s-purge'))?.state).toBe('PURGE_COMPLETE');
  });

  it('quarantine TTL: fresh kept, expired deleted', async () => {
    const exportRepo = new LocalCsvExportRepository(db as never);
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    fsState.dirs.add(`${DOC}export-quarantine/`);
    const fresh = `${DOC}export-quarantine/fresh.bin`;
    const old = `${DOC}export-quarantine/old.bin`;
    putFile(fresh, 1, 1000);
    putFile(old, 2, DEFAULT_ARTIFACT_RETENTION_TTLS.quarantineMs + 1000);
    const reconciler = new ExportArtifactReconciler({
      captureRepo: { getSession: async () => null } as never,
      exportRepo,
      attemptRepo,
      prepRepo: null,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    await reconciler.runBounded({ maxFiles: 20, maxDurationMs: 5_000 });
    expect(fsState.files.has(fresh)).toBe(true);
    expect(fsState.files.has(old)).toBe(false);
  });

  it('two concurrent purges: one runs, other skips or completes idempotently', async () => {
    await seedSession('s-conc');
    const exportRepo = new LocalCsvExportRepository(db as never);
    const attemptRepo = new LocalExportAttemptRepository(db as never);
    const purgeTaskRepo = new SessionPurgeTaskRepository(db as never);
    const purge = new SessionArtifactPurgeCoordinator({
      attemptRepo,
      exportRepo,
      purgeTaskRepo,
      exportPrepQueue: {
        cancelAndDrainSession: jest.fn(async () => undefined),
        purgeSessionArtifacts: jest.fn(async () => undefined),
      } as never,
      getRoots: () => ({ documentDirectory: DOC, cacheDirectory: CACHE }),
    });
    const [a, b] = await Promise.all([
      purge.purgeSession('s-conc'),
      purge.purgeSession('s-conc'),
    ]);
    expect([a, b].some((r) => r.skippedActive === 1 || r.failed === 0)).toBe(true);
  });
});
