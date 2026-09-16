/**
 * Real SQLite (node:sqlite) tests for export_prep CAS, v34→v35 migration, concurrent backfill.
 * Map-backed harnesses are unit-only — this file is the concurrency/SQL evidence.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { ExportPrepRepository } from '../src/database/repositories/exportPrepRepository';
import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { MIGRATIONS } from '../src/database/migrations/migrations';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';

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

function openTempDb(): { db: AsyncDb; filePath: string; sync: DatabaseSync } {
  const filePath = path.join(
    os.tmpdir(),
    `export-prep-${Date.now()}-${Math.random().toString(16).slice(2)}.db`,
  );
  const sync = new DatabaseSync(filePath);
  sync.exec('PRAGMA foreign_keys = ON;');
  sync.exec('PRAGMA journal_mode = WAL;');
  return { db: wrapDatabaseSync(sync), filePath, sync };
}

function applyMigrationSql(sync: DatabaseSync, sql: string): void {
  // Split on semicolons that end statements; ignore empty chunks.
  for (const chunk of sql.split(';')) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;
    sync.exec(`${trimmed};`);
  }
}

function applyMigrationsThrough(sync: DatabaseSync, maxVersion: number): void {
  for (const m of MIGRATIONS) {
    if (m.version > maxVersion) break;
    applyMigrationSql(sync, m.sql);
    sync.exec(
      `CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY NOT NULL);`,
    );
    sync.prepare(`INSERT OR IGNORE INTO schema_migrations(version) VALUES (?);`).run(m.version);
  }
}

describe('export_prep real SQLite', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  it('CAS requeue fails after renew on a second connection', async () => {
    const { db, filePath, sync } = openTempDb();
    try {
      applyMigrationsThrough(sync, 35);
      const now = new Date().toISOString();
      await db.runAsync(
        `INSERT INTO capture_sessions (
           id, inventory_id, inventory_name, aisle_id, aisle_name, status,
           started_at, scan_cursor_date_added, scan_cursor_asset_id,
           last_valid_cursor_date_added, last_valid_cursor_asset_id,
           created_at, updated_at
         ) VALUES (?, 'inv', 'Inv', 'aisle', 'A1', 'review', ?, 0, '', 0, '', ?, ?);`,
        's1',
        now,
        now,
        now,
      );

      const repoA = new ExportPrepRepository(db as never);
      await repoA.enqueueIdempotent({
        capturePhotoId: 'p1',
        captureSessionId: 's1',
        sourceUri: 'file://source/p1.jpg',
        sourceFingerprint: 'fp',
        exportFileName: '0001_p1.jpg',
      });
      const claimed = await repoA.claimNext('s1');
      expect(claimed?.lease_token).toBeTruthy();

      // Expire lease via raw SQL
      await db.runAsync(
        `UPDATE export_prep_jobs SET lease_expires_at = ? WHERE capture_photo_id = ?;`,
        '2000-01-01T00:00:00.000Z',
        'p1',
      );
      const observed = (await repoA.getByPhotoId('p1'))!;

      const syncB = new DatabaseSync(filePath);
      const dbB = wrapDatabaseSync(syncB);
      const repoB = new ExportPrepRepository(dbB as never);

      await repoA.renewLease('p1', claimed!.lease_token!, 120_000);
      const cas = await repoB.requeueExpiredLease(observed, {
        sourceUri: 'file://source/p1.jpg',
        sourceFingerprint: 'fp',
        exportFileName: '0001_p1.jpg',
      });
      expect(cas.requeued).toBe(false);
      expect(cas.job.lease_token).toBe(claimed!.lease_token);
      expect(cas.job.status).toBe('PREPARING');
      syncB.close();
    } finally {
      db.close();
      try {
        fs.unlinkSync(filePath);
        fs.unlinkSync(`${filePath}-wal`);
        fs.unlinkSync(`${filePath}-shm`);
      } catch {
        /* ignore */
      }
    }
  });

  it('v34→v35 migration then backfill materializes jobs; concurrent backfills stay PK-safe', async () => {
    const { db, filePath, sync } = openTempDb();
    try {
      applyMigrationsThrough(sync, 34);
      const now = new Date().toISOString();
      await db.runAsync(
        `INSERT INTO capture_sessions (
           id, inventory_id, inventory_name, aisle_id, aisle_name, status,
           started_at, scan_cursor_date_added, scan_cursor_asset_id,
           last_valid_cursor_date_added, last_valid_cursor_asset_id,
           created_at, updated_at
         ) VALUES (?, 'inv', 'Inv', 'aisle', 'A1', 'local_completed', ?, 0, '', 0, '', ?, ?);`,
        'hist-1',
        now,
        now,
        now,
      );
      await db.runAsync(
        `INSERT INTO capture_photos (
           id, capture_session_id, asset_id, uri, display_name, mime_type,
           size, width, height, date_added, date_modified, status,
           sequence_number, created_at, updated_at
         ) VALUES (?, 'hist-1', '100', 'file://source/h1.jpg', 'h1.jpg', 'image/jpeg',
           12, 1, 1, 1, 1, 'stable', 1, ?, ?);`,
        'hist-1:100',
        now,
        now,
      );
      await db.runAsync(
        `INSERT INTO capture_photos (
           id, capture_session_id, asset_id, uri, display_name, mime_type,
           size, width, height, date_added, date_modified, status,
           sequence_number, created_at, updated_at
         ) VALUES (?, 'hist-1', '101', 'file://source/h2.jpg', 'h2.jpg', 'image/jpeg',
           12, 1, 1, 2, 2, 'stable', 2, ?, ?);`,
        'hist-1:101',
        now,
        now,
      );

      const before = await db.getFirstAsync<{ name: string }>(
        `SELECT name FROM sqlite_master WHERE type='table' AND name='export_prep_jobs';`,
      );
      expect(before).toBeNull();

      const v35 = MIGRATIONS.find((m) => m.version === 35)!;
      applyMigrationSql(sync, v35.sql);
      sync.prepare(`INSERT OR IGNORE INTO schema_migrations(version) VALUES (?);`).run(35);

      db.close();

      const sync2 = new DatabaseSync(filePath);
      sync2.exec('PRAGMA foreign_keys = ON;');
      const db2 = wrapDatabaseSync(sync2);
      const after = await db2.getFirstAsync<{ name: string }>(
        `SELECT name FROM sqlite_master WHERE type='table' AND name='export_prep_jobs';`,
      );
      expect(after?.name).toBe('export_prep_jobs');

      const photos = [
        {
          id: 'hist-1:100',
          capture_session_id: 'hist-1',
          status: 'stable',
          uri: 'file://source/h1.jpg',
          size: 12,
          width: 1,
          height: 1,
          sequence_number: 1,
          display_name: 'h1.jpg',
        },
        {
          id: 'hist-1:101',
          capture_session_id: 'hist-1',
          status: 'stable',
          uri: 'file://source/h2.jpg',
          size: 12,
          width: 1,
          height: 1,
          sequence_number: 2,
          display_name: 'h2.jpg',
        },
      ];

      const repo = new ExportPrepRepository(db2 as never);
      const queue = new ExportPrepQueue({
        prepRepo: repo,
        captureRepo: {
          getSession: async () => ({
            id: 'hist-1',
            active_freeze_id: null,
            upload_policy: 'MANUAL',
          }),
          listPhotos: async () => photos,
          listFreezePhotos: async () => photos,
          getPhotoById: async (id: string) => photos.find((p) => p.id === id) ?? null,
        } as never,
        draftRepo: { listForSession: async () => [] } as never,
        localCodeScan: null,
        localCodeScanEnabled: false,
      });
      // Backfill-only: stop workers so closing the DB cannot race processJob.
      queue.stop();

      const [a, b] = await Promise.all([
        queue.ensureJobsForEligiblePhotos('hist-1', { reason: 'REVIEW_OPEN' }),
        queue.ensureJobsForEligiblePhotos('hist-1', { reason: 'EXPORT_PREFLIGHT' }),
      ]);
      const jobs = await repo.listForSession('hist-1');
      expect(jobs).toHaveLength(2);
      expect(new Set(jobs.map((j) => j.capture_photo_id)).size).toBe(2);
      expect(a.createdJobs + b.createdJobs).toBeGreaterThanOrEqual(1);
      for (const j of jobs) {
        expect(j.attempt_count).toBeGreaterThanOrEqual(0);
        expect(
          ['QUEUED', 'PREPARING', 'SCANNING', 'VALIDATING', 'READY'].includes(j.status),
        ).toBe(true);
      }

      const third = await queue.ensureJobsForEligiblePhotos('hist-1', { reason: 'FINISH' });
      expect(third.createdJobs).toBe(0);
      expect((await repo.listForSession('hist-1')).length).toBe(2);

      // Two drain observers coalesce; READY jobs → exportable without mutating rows.
      for (const id of ['hist-1:100', 'hist-1:101']) {
        await db2.runAsync(
          `UPDATE export_prep_jobs SET
             status = 'READY', staging_uri = ?, export_file_name = ?, size_bytes = 12,
             sha256 = ?, ready_at = ?, updated_at = ?
           WHERE capture_photo_id = ?;`,
          `file:///docs/export-staging/hist-1/photos/${id}.jpg`,
          `0001_${id}.jpg`,
          'c'.repeat(64),
          now,
          now,
          id,
        );
      }
      // Fresh observer queue: workers stopped on prior instance; mock ensure so READY
      // rows are not invalidated by missing staging files in this unit fixture.
      const drainQueue = new ExportPrepQueue({
        prepRepo: repo,
        captureRepo: {
          getSession: async () => ({
            id: 'hist-1',
            active_freeze_id: null,
            upload_policy: 'MANUAL',
          }),
          listPhotos: async () => photos,
          listFreezePhotos: async () => photos,
          getPhotoById: async (id: string) => photos.find((p) => p.id === id) ?? null,
        } as never,
        draftRepo: { listForSession: async () => [] } as never,
        localCodeScan: null,
        localCodeScanEnabled: false,
      });
      jest.spyOn(drainQueue, 'ensureJobsForEligiblePhotos').mockResolvedValue({
        sessionId: 'hist-1',
        reason: 'RECOVERY',
        eligiblePhotos: 2,
        existingJobs: 2,
        createdJobs: 0,
        requeuedJobs: 0,
        invalidatedReadyJobs: 0,
        excludedJobs: 0,
        missingSourcePhotos: 0,
        partialErrors: [],
        durationMs: 0,
      });
      const [d1, d2] = await Promise.all([
        drainQueue.waitUntilExportable('hist-1', {
          timeoutMs: 2_000,
          pollMs: 50,
          reason: 'RECOVERY',
          producerBarrierCompleted: true,
          allowLegacyWithoutFreeze: true,
        }),
        drainQueue.waitUntilExportable('hist-1', {
          timeoutMs: 2_000,
          pollMs: 50,
          reason: 'RECOVERY',
          producerBarrierCompleted: true,
          allowLegacyWithoutFreeze: true,
        }),
      ]);
      expect(d1.exportable).toBe(true);
      expect(d2.exportable).toBe(true);
      expect(d1.sessionExists).toBe(true);
      expect(d1.sessionId).toBe('hist-1');
      drainQueue.stop();
      queue.stop();
      // Allow any in-flight write-gate work to settle before closing SQLite.
      await new Promise((r) => setTimeout(r, 50));

      sync2.close();
    } finally {
      try {
        fs.unlinkSync(filePath);
        fs.unlinkSync(`${filePath}-wal`);
        fs.unlinkSync(`${filePath}-shm`);
      } catch {
        /* ignore */
      }
    }
  });

  it('v36 concurrent local_csv_exports inserts for same session+fingerprint stay unique', async () => {
    const { db, filePath, sync } = openTempDb();
    try {
      applyMigrationsThrough(sync, 36);
      const { LocalCsvExportRepository } = await import(
        '../src/database/repositories/localCsvExportRepository'
      );
      const now = new Date().toISOString();
      await db.runAsync(
        `INSERT INTO capture_sessions (
           id, inventory_id, inventory_name, aisle_id, aisle_name, status,
           started_at, scan_cursor_date_added, scan_cursor_asset_id,
           last_valid_cursor_date_added, last_valid_cursor_asset_id,
           created_at, updated_at, export_packaging_mode
         ) VALUES (?, 'inv', 'Inv', 'aisle', 'A1', 'local_completed', ?, 0, '', 0, '', ?, ?, 'STAGING_REQUIRED');`,
        's-export',
        now,
        now,
        now,
      );
      const repo = new LocalCsvExportRepository(db as never);
      const fp = 'content-fp-1';
      const rowA = {
        id: 'id-a',
        export_id: 'export-a',
        schema_version: '1.1',
        scope: 'session',
        capture_session_id: 's-export',
        inventory_id: 'inv',
        aisle_id: 'aisle',
        row_count: 1,
        checksum_sha256: 'a'.repeat(64),
        content_fingerprint: fp,
        file_uri: 'file:///a.csv',
        freeze_id: 'f1',
        zip_size_bytes: 10,
        zip_sha256: 'b'.repeat(64),
        package_checksum_sha256: fp,
        exported_at: now,
        shared_at: null,
        created_at: now,
        updated_at: now,
      };
      const rowB = { ...rowA, id: 'id-b', export_id: 'export-b', file_uri: 'file:///b.csv' };
      const [okA, okB] = await Promise.all([repo.tryInsert(rowA), repo.tryInsert(rowB)]);
      expect(okA || okB).toBe(true);
      expect(okA && okB).toBe(false);
      const rows = await repo.listForSession('s-export');
      expect(rows).toHaveLength(1);
      expect(rows[0]!.content_fingerprint).toBe(fp);
    } finally {
      db.close();
      try {
        fs.unlinkSync(filePath);
        fs.unlinkSync(`${filePath}-wal`);
        fs.unlinkSync(`${filePath}-shm`);
      } catch {
        /* ignore */
      }
    }
  });
});
